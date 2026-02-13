# app/services/db_service.py
from __future__ import annotations

import os
import json
import sqlite3
from typing import Any, Dict, List, Optional

# Auth hashing (passlib recommended)
try:
    from passlib.context import CryptContext

    _PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")
except Exception:
    _PWD_CONTEXT = None  # fallback handled below

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # project/app -> project
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
DB_PATH = os.getenv("DB_PATH", os.path.join(DATA_DIR, "receipts.db"))

os.makedirs(DATA_DIR, exist_ok=True)

# ------------------------------------------------------------------------------
# DB helpers
# ------------------------------------------------------------------------------


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
    cols = {r["name"] for r in rows}
    return column in cols


def _ensure_receipts_business_id(conn: sqlite3.Connection) -> None:
    """
    For existing DBs: add business_id to receipts if missing.
    SQLite can add a column with NOT NULL only if DEFAULT is provided.
    """
    if not _table_has_column(conn, "receipts", "business_id"):
        conn.execute("ALTER TABLE receipts ADD COLUMN business_id INTEGER NOT NULL DEFAULT 1;")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_receipts_business_id ON receipts(business_id);")


def _ensure_receipts_archive_fields(conn: sqlite3.Connection) -> None:
    """
    Add archive/export fields to receipts if missing.
    status: 'active' | 'archived'
    exported_at / archived_at are ISO-ish timestamps stored as TEXT (sqlite datetime()).
    """
    if not _table_has_column(conn, "receipts", "status"):
        conn.execute("ALTER TABLE receipts ADD COLUMN status TEXT NOT NULL DEFAULT 'active';")
    if not _table_has_column(conn, "receipts", "exported_at"):
        conn.execute("ALTER TABLE receipts ADD COLUMN exported_at TEXT;")
    if not _table_has_column(conn, "receipts", "archived_at"):
        conn.execute("ALTER TABLE receipts ADD COLUMN archived_at TEXT;")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_receipts_business_status ON receipts(business_id, status);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_receipts_business_needs_review ON receipts(business_id, needs_review);")


def _safe_json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return "[]"


# ------------------------------------------------------------------------------
# Init / schema
# ------------------------------------------------------------------------------


def init_db() -> None:
    """
    Creates tables if missing.
    Also performs minimal safe schema upgrades (adds business_id, archive/export fields).
    """
    with _connect() as conn:
        # --- Core receipts table (existing structure preserved) ---
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_filename TEXT NOT NULL,
                saved_json_path TEXT NOT NULL,
                vendor TEXT,
                date TEXT,
                total REAL,
                category TEXT,
                needs_review INTEGER DEFAULT 0,
                flags_json TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now'))
            );
            """
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_receipts_needs_review ON receipts(needs_review);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_receipts_vendor ON receipts(vendor);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_receipts_date ON receipts(date);")

        # --- Users / Businesses / Memberships (for business scoping) ---
        # IMPORTANT: password_hash is kept NOT NULL for compatibility, but magic-link users
        # will get a sentinel value ("magic") and will authenticate via codes, not passwords.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS businesses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memberships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                business_id INTEGER NOT NULL,
                role TEXT DEFAULT 'owner',
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, business_id)
            );
            """
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_memberships_user_id ON memberships(user_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memberships_business_id ON memberships(business_id);")

        # --- (Optional legacy) Auth0 identities mapping ---
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_identities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                auth0_sub TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_identities_user_id ON auth_identities(user_id);")

        # --- Upgrade: receipts.business_id + archive/export fields ---
        _ensure_receipts_business_id(conn)
        _ensure_receipts_archive_fields(conn)

        # --- Ensure at least one default business exists for legacy rows ---
        row = conn.execute("SELECT id FROM businesses ORDER BY id ASC LIMIT 1;").fetchone()
        if not row:
            conn.execute("INSERT INTO businesses (name) VALUES (?);", ("Default Business",))
            conn.execute("UPDATE receipts SET business_id = 1 WHERE business_id IS NULL;")

        conn.commit()


# ------------------------------------------------------------------------------
# Auth helpers (password-based remains for legacy; magic-link uses bootstrap below)
# ------------------------------------------------------------------------------


def _hash_password(password: str) -> str:
    if _PWD_CONTEXT is not None:
        return _PWD_CONTEXT.hash(password)

    # Fallback (should not be used if passlib is installed)
    import hashlib, secrets

    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return f"pbkdf2_sha256${salt}${dk.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    if _PWD_CONTEXT is not None:
        try:
            return _PWD_CONTEXT.verify(password, stored_hash)
        except Exception:
            return False

    # Fallback verify
    try:
        import hashlib

        algo, salt, hex_dk = stored_hash.split("$", 2)
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
        return dk.hex() == hex_dk
    except Exception:
        return False


def create_user(email: str, password: str) -> int:
    """
    Creates a new user and returns user_id.
    Raises sqlite3.IntegrityError if email exists.
    """
    init_db()
    email_norm = email.strip().lower()
    pw_hash = _hash_password(password)

    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?);",
            (email_norm, pw_hash),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    init_db()
    email_norm = email.strip().lower()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?;", (email_norm,)).fetchone()
        return dict(row) if row else None


def verify_user_credentials(email: str, password: str) -> Optional[int]:
    """
    Returns user_id if valid, else None.
    """
    user = get_user_by_email(email)
    if not user:
        return None
    if not _verify_password(password, user["password_hash"]):
        return None
    return int(user["id"])


# ------------------------------------------------------------------------------
# Auth0 legacy mapping (kept for compatibility)
# ------------------------------------------------------------------------------


def get_user_id_by_auth0_sub(auth0_sub: str) -> Optional[int]:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT user_id FROM auth_identities WHERE auth0_sub = ? LIMIT 1;",
            (auth0_sub,),
        ).fetchone()
        return int(row["user_id"]) if row else None


def get_or_create_user_by_auth0_sub(auth0_sub: str) -> int:
    """
    Maps an Auth0 subject (sub) to an internal users.id.
    Creates a placeholder user row if needed (no email/password required for OAuth flow).
    """
    init_db()
    auth0_sub = (auth0_sub or "").strip()
    if not auth0_sub:
        raise ValueError("auth0_sub is required")

    existing = get_user_id_by_auth0_sub(auth0_sub)
    if existing:
        return existing

    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?);",
            (f"auth0:{auth0_sub}", "oauth"),
        )
        user_id = int(cur.lastrowid)

        conn.execute(
            "INSERT INTO auth_identities (user_id, auth0_sub) VALUES (?, ?);",
            (user_id, auth0_sub),
        )
        conn.commit()
        return user_id


# ------------------------------------------------------------------------------
# Magic-link alignment helpers (THIS is what fixes your 403 + business scoping)
# ------------------------------------------------------------------------------


def get_or_create_user_for_magic(email: str) -> int:
    """
    Magic-link flow needs a DB user_id (INTEGER) even though no password is used.
    This upserts a user row keyed by email and returns users.id.
    """
    init_db()
    email_norm = (email or "").strip().lower()
    if not email_norm or "@" not in email_norm:
        raise ValueError("Valid email required")

    with _connect() as conn:
        row = conn.execute("SELECT id FROM users WHERE email = ?;", (email_norm,)).fetchone()
        if row:
            return int(row["id"])

        # Create user with sentinel password_hash; magic-link auth does not use it.
        cur = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?);",
            (email_norm, "magic"),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_or_create_single_business_for_user(user_id: int, default_name: str = "My Business") -> int:
    """
    Ensures the user has at least one business and membership(owner).
    Returns the first business id (INTEGER).
    """
    init_db()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT b.id
            FROM businesses b
            JOIN memberships m ON m.business_id = b.id
            WHERE m.user_id = ?
            ORDER BY b.id ASC
            LIMIT 1;
            """,
            (int(user_id),),
        ).fetchone()

        if row:
            return int(row["id"])

        cur = conn.execute(
            "INSERT INTO businesses (name) VALUES (?);",
            ((default_name or "My Business").strip(),),
        )
        business_id = int(cur.lastrowid)

        conn.execute(
            "INSERT OR IGNORE INTO memberships (user_id, business_id, role) VALUES (?, ?, ?);",
            (int(user_id), int(business_id), "owner"),
        )
        conn.commit()
        return business_id


def bootstrap_magic_login(email: str, default_business_name: str = "My Business") -> Dict[str, int]:
    """
    One-call helper you should invoke from /auth/verify_code in main.py.
    Returns {user_id: int, business_id: int} that your token can carry.

    This is the missing bridge that fixes:
      - Business ID must be an integer
      - 403 No access to this business on /upload
    """
    uid = get_or_create_user_for_magic(email)
    bid = get_or_create_single_business_for_user(uid, default_name=default_business_name)
    return {"user_id": int(uid), "business_id": int(bid)}


# ------------------------------------------------------------------------------
# Business helpers (used by main.py endpoints)
# ------------------------------------------------------------------------------


def create_business(name: str) -> int:
    init_db()
    with _connect() as conn:
        cur = conn.execute("INSERT INTO businesses (name) VALUES (?);", (name.strip(),))
        conn.commit()
        return int(cur.lastrowid)


def add_membership(user_id: int, business_id: int, role: str = "owner") -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO memberships (user_id, business_id, role) VALUES (?, ?, ?);",
            (int(user_id), int(business_id), (role or "owner")),
        )
        conn.commit()


def list_businesses_for_user(user_id: int) -> List[Dict[str, Any]]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT b.id, b.name
            FROM businesses b
            JOIN memberships m ON m.business_id = b.id
            WHERE m.user_id = ?
            ORDER BY b.id ASC;
            """,
            (int(user_id),),
        ).fetchall()
        return [{"id": int(r["id"]), "name": r["name"]} for r in rows]


def user_has_business_access(user_id: int, business_id: int) -> bool:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM memberships WHERE user_id = ? AND business_id = ? LIMIT 1;",
            (int(user_id), int(business_id)),
        ).fetchone()
        return bool(row)


# ------------------------------------------------------------------------------
# Receipt operations (business locked + archive/export)
# ------------------------------------------------------------------------------


def insert_receipt(
    parsed: Dict[str, Any],
    source_filename: str,
    saved_json_path: str,
    business_id: int = 1,
) -> int:
    """
    Inserts a receipt record and returns the new DB id.
    Store summary fields for quick querying.
    """
    init_db()

    vendor = parsed.get("vendor")
    date = parsed.get("date")
    total = parsed.get("total")
    category = parsed.get("category")
    needs_review = 1 if bool(parsed.get("needs_review")) else 0
    flags_json = _safe_json(parsed.get("flags") or [])

    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO receipts (
                business_id,
                status,
                source_filename,
                saved_json_path,
                vendor,
                date,
                total,
                category,
                needs_review,
                flags_json
            )
            VALUES (?, 'active', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(business_id),
                source_filename,
                saved_json_path,
                vendor,
                date,
                total,
                category,
                needs_review,
                flags_json,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_receipt_saved_path(receipt_id: int, saved_json_path: str, business_id: int = 1) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "UPDATE receipts SET saved_json_path = ? WHERE id = ? AND business_id = ?;",
            (saved_json_path, int(receipt_id), int(business_id)),
        )
        conn.commit()


def update_receipt_review_fields(
    receipt_id: int,
    *,
    business_id: int = 1,
    vendor: Optional[str] = None,
    date: Optional[str] = None,
    total: Optional[float] = None,
    category: Optional[str] = None,
    needs_review: Optional[bool] = None,
    flags: Optional[List[str]] = None,
) -> None:
    """
    Updates selected searchable fields for THIS business only.
    """
    init_db()

    fields: List[str] = []
    values: List[Any] = []

    if vendor is not None:
        fields.append("vendor = ?")
        values.append(vendor)

    if date is not None:
        fields.append("date = ?")
        values.append(date)

    if total is not None:
        fields.append("total = ?")
        values.append(total)

    if category is not None:
        fields.append("category = ?")
        values.append(category)

    if needs_review is not None:
        fields.append("needs_review = ?")
        values.append(1 if needs_review else 0)

    if flags is not None:
        fields.append("flags_json = ?")
        values.append(_safe_json(flags))

    if not fields:
        return

    values.extend([int(receipt_id), int(business_id)])

    with _connect() as conn:
        conn.execute(
            f"UPDATE receipts SET {', '.join(fields)} WHERE id = ? AND business_id = ?;",
            tuple(values),
        )
        conn.commit()


def get_receipt_row(receipt_id: int, business_id: int = 1) -> Optional[Dict[str, Any]]:
    """
    Fetch a single receipt row locked to business_id.
    """
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM receipts WHERE id = ? AND business_id = ?;",
            (int(receipt_id), int(business_id)),
        ).fetchone()
        if not row:
            return None

        d = dict(row)
        try:
            d["flags"] = json.loads(d.get("flags_json") or "[]")
        except Exception:
            d["flags"] = []

        d["needs_review"] = bool(d.get("needs_review"))
        d["filename"] = d.get("source_filename")
        return d


def list_receipts(
    limit: int = 50,
    business_id: int = 1,
    status: str = "active",  # "active" | "archived" | "all"
) -> List[Dict[str, Any]]:
    """
    Returns lightweight records for /receipts endpoint (DB-backed), scoped to business.
    """
    init_db()
    status_norm = (status or "active").strip().lower()
    if status_norm not in ("active", "archived", "all"):
        status_norm = "active"

    where = "WHERE business_id = ?"
    params: List[Any] = [int(business_id)]

    if status_norm != "all":
        where += " AND status = ?"
        params.append(status_norm)

    params.append(max(1, int(limit)))

    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT id, business_id, status, exported_at, archived_at,
                   source_filename, vendor, date, total, category,
                   needs_review, flags_json, created_at
            FROM receipts
            {where}
            ORDER BY id DESC
            LIMIT ?;
            """,
            tuple(params),
        ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        try:
            d["flags"] = json.loads(d.get("flags_json") or "[]")
        except Exception:
            d["flags"] = []
        d["needs_review"] = bool(d.get("needs_review"))
        d["filename"] = d.pop("source_filename", None)
        d.pop("flags_json", None)
        out.append(d)
    return out


def list_review_queue(limit: int = 50, business_id: int = 1) -> List[Dict[str, Any]]:
    """
    DB-backed review queue (active receipts only), scoped to business.
    """
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, business_id, status, exported_at, archived_at,
                   source_filename, vendor, date, total, category,
                   needs_review, flags_json, created_at
            FROM receipts
            WHERE business_id = ? AND status = 'active' AND needs_review = 1
            ORDER BY id DESC
            LIMIT ?;
            """,
            (int(business_id), max(1, int(limit))),
        ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        try:
            d["flags"] = json.loads(d.get("flags_json") or "[]")
        except Exception:
            d["flags"] = []
        d["needs_review"] = True
        d["filename"] = d.pop("source_filename", None)
        d.pop("flags_json", None)
        out.append(d)
    return out


# ------------------------------------------------------------------------------
# Archive / export helpers
# ------------------------------------------------------------------------------


def archive_receipts(receipt_ids: List[int], business_id: int = 1, mark_exported: bool = True) -> int:
    """
    Archives receipts for THIS business only.
    """
    init_db()
    ids = [int(x) for x in (receipt_ids or []) if str(x).strip().isdigit()]
    if not ids:
        return 0

    placeholders = ",".join(["?"] * len(ids))
    sets = ["status = 'archived'", "archived_at = datetime('now')"]
    if mark_exported:
        sets.append("exported_at = COALESCE(exported_at, datetime('now'))")

    sql = f"""
        UPDATE receipts
        SET {', '.join(sets)}
        WHERE business_id = ? AND id IN ({placeholders});
    """
    params: List[Any] = [int(business_id)] + ids

    with _connect() as conn:
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return int(cur.rowcount or 0)


def unarchive_receipts(receipt_ids: List[int], business_id: int = 1) -> int:
    """
    Optional: restore archived receipts back to active for THIS business only.
    """
    init_db()
    ids = [int(x) for x in (receipt_ids or []) if str(x).strip().isdigit()]
    if not ids:
        return 0

    placeholders = ",".join(["?"] * len(ids))
    sql = f"""
        UPDATE receipts
        SET status = 'active',
            archived_at = NULL
        WHERE business_id = ? AND id IN ({placeholders});
    """
    params: List[Any] = [int(business_id)] + ids

    with _connect() as conn:
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return int(cur.rowcount or 0)
