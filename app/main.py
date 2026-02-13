# app/main.py
from __future__ import annotations

import os
import json
from uuid import uuid4
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from fastapi import Request, Header, Depends
from fastapi.responses import RedirectResponse
import secrets
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
import time

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    HTTPException,
    Depends,
    APIRouter,
    Header,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer

from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# =========================
# Pipeline / existing services
# =========================
from app.schemas import (
    UploadResponse,
    BatchUploadResponse,
    BatchUploadResult,
    ReceiptReviewPatch,
    ReceiptNormalized,
    OCRMeta,
)

from app.services.ocr_service import extract_text
from app.services.parser_service import parse_receipt
from app.services.receipt_normalizer import normalize_receipt
from app.services.storage_service import (
    save_receipt_payload,
    load_receipt_payload,
)

from dataclasses import asdict, is_dataclass
from pathlib import Path
import shutil
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# =========================
# Optional features
# =========================
from app.services.categorizer_service import categorize_purchase

# =========================
# DB service (single import style — IMPORTANT)
# =========================
from app.services import db_service
from fastapi.security import OAuth2PasswordBearer
import requests
from functools import lru_cache
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True))
ENV_PATH = Path(__file__).resolve().parents[1]/".env"
print("Loaded .env from", ENV_PATH)


# Leave your existing receipt endpoints BELOW this block as-is.
# IMPORTANT: this block defines:
#   - /auth/request_code
#   - /auth/verify_code
#   - /me
#   - get_current_context() dependency
#
# If you already have /me, delete yours and keep this one.

import os
import time
import json
import base64
import hashlib
import hmac
import secrets
from typing import Dict, Any, Optional

from fastapi import Header, HTTPException, Depends
from pydantic import BaseModel

app = FastAPI(title="SmallBiz Bookkeeping Engine", version="1.0")

# ----------------------------
# MAGIC CODE STORE (DEV SIMPLE)
# ----------------------------
_CODE_TTL_SECONDS = int(os.getenv("LOGIN_CODE_TTL_SECONDS", "600"))  # 10 min
_codes: Dict[str, Dict[str, Any]] = {}  # email -> {code_hash, exp}

def _norm_email(email: str) -> str:
    return (email or "").strip().lower()

def _hash_code(code: str, salt: str) -> str:
    return hashlib.sha256((salt + ":" + code).encode("utf-8")).hexdigest()

def _issue_code(email: str) -> str:
    email = _norm_email(email)
    code = f"{secrets.randbelow(1000000):06d}"
    salt = os.getenv("LOGIN_CODE_SALT", "dev-salt-change-me")
    _codes[email] = {
        "code_hash": _hash_code(code, salt),
        "exp": int(time.time()) + _CODE_TTL_SECONDS,
    }
    return code

def _verify_code(email: str, code: str) -> bool:
    email = _norm_email(email)
    rec = _codes.get(email)
    if not rec:
        return False
    if int(time.time()) > int(rec.get("exp", 0)):
        _codes.pop(email, None)
        return False
    salt = os.getenv("LOGIN_CODE_SALT", "dev-salt-change-me")
    ok = hmac.compare_digest(rec["code_hash"], _hash_code(code, salt))
    if ok:
        _codes.pop(email, None)
    return ok

def send_magic_link_email(to_email: str, magic_link: str):
    message = Mail(
        from_email=os.getenv("EMAIL_FROM"),
        to_emails=to_email,
        subject="Your SmallBiz login link",
        html_content=f"""
        <p>Click the link below to sign in:</p>
        <p><a href="{magic_link}">{magic_link}</a></p>
        <p>This link expires shortly.</p>
        """
    )

    try:
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        sg.send(message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email send failed: {e}")

# ----------------------------
# TOKEN (SIGNED, NO EXTERNAL LIBS)
# Format: base64url(payload_json) + "." + hex_hmac_sha256
# ----------------------------
_TOKEN_TTL_SECONDS = int(os.getenv("ACCESS_TOKEN_TTL_SECONDS", "86400"))  # 24h
_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET", "dev-secret-change-me")

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

def _b64url_decode(s: str) -> bytes:
    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("utf-8"))

def _sign(msg: bytes) -> str:
    return hmac.new(_TOKEN_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()

def create_access_token(payload: Dict[str, Any]) -> str:
    now = int(time.time())
    body = dict(payload)
    body["iat"] = now
    body["exp"] = now + _TOKEN_TTL_SECONDS
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    p = _b64url(raw).encode("utf-8")
    sig = _sign(p)
    return p.decode("utf-8") + "." + sig

def verify_access_token(token: str) -> Dict[str, Any]:
    try:
        p_b64, sig = token.split(".", 1)
        p_bytes = p_b64.encode("utf-8")
        if not hmac.compare_digest(_sign(p_bytes), sig):
            raise ValueError("bad signature")
        body = json.loads(_b64url_decode(p_b64).decode("utf-8"))
        if int(time.time()) > int(body.get("exp", 0)):
            raise ValueError("expired")
        return body
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# ----------------------------
# BUSINESS SEPARATION
# You can replace this with your DB mapping later.
# For now: stable business_id per email.
# ----------------------------
def resolve_business_id(email: str) -> str:
    email = _norm_email(email)
    # stable 12 chars
    return "biz_" + hashlib.sha1(email.encode("utf-8")).hexdigest()[:12]

def resolve_user_id(email: str) -> str:
    email = _norm_email(email)
    return "usr_" + hashlib.sha1(email.encode("utf-8")).hexdigest()[:12]

# ----------------------------
# EMAIL SENDER (OPTIONAL)
# If not configured, it prints the code in backend console (dev-friendly).
# ----------------------------
def send_login_code(email: str, code: str) -> None:
    import os
    import requests
    from email.utils import parseaddr

    sg_key = (os.getenv("SENDGRID_API_KEY") or "").strip()
    email_from_raw = (os.getenv("EMAIL_FROM") or "").strip()
    ui_base_url = (os.getenv("UI_BASE_URL") or "").strip()

    print("SENDGRID_API_KEY present:", bool(sg_key))
    print("EMAIL_FROM raw:", repr(email_from_raw))

    from_name, from_email = parseaddr(email_from_raw)

    if not sg_key:
        print("❌ SENDGRID_API_KEY missing")
        return

    if not from_email:
        print("❌ EMAIL_FROM invalid:", email_from_raw)
        return

    subject = "Your login code"
    body = f"Your login code is: {code}"
    if ui_base_url:
        body += f"\n\nOpen the app: {ui_base_url}"

    payload = {
        "personalizations": [{"to": [{"email": email}]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }

    headers = {
        "Authorization": f"Bearer {sg_key}",
        "Content-Type": "application/json",
    }

    print("➡️ Sending email to:", email)
    r = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers=headers,
        json=payload,
        timeout=20,
    )

    print("📨 SendGrid status:", r.status_code)
    print("📨 SendGrid response:", r.text)

    r.raise_for_status()
# ----------------------------
# REQUEST/RESPONSE MODELS
# ----------------------------
class RequestCodeIn(BaseModel):
    email: str

class VerifyCodeIn(BaseModel):
    email: str
    code: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class BusinessCreateIn(BaseModel):
    name:str

# ----------------------------
# AUTH ROUTES
# ----------------------------
@app.post("/auth/request_code")
def auth_request_code(inp: RequestCodeIn):
    email = _norm_email(inp.email)
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email required")
    code = _issue_code(email)
    send_login_code(email, code)
    return {"ok": True}

@app.post("/auth/verify_code", response_model=TokenOut)
def auth_verify_code(inp: VerifyCodeIn):
    email = _norm_email(inp.email)
    code = (inp.code or "").strip()

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email required")
    if not code or len(code) != 6 or not code.isdigit():
        raise HTTPException(status_code=400, detail="6-digit code required")
    if not _verify_code(email, code):
        raise HTTPException(status_code=401, detail="Invalid code")

    # ✅ Use DB-backed identity so the rest of main.py + db_service works
    # Ensure db schema exists
    db_service.init_db()

    # Get or create DB user
    user_row = db_service.get_user_by_email(email)
    if user_row:
        db_user_id = int(user_row["id"])
    else:
        # Create a placeholder user row for magic-link auth (no password needed)
        # Uses existing users table schema
        with db_service._connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?);",
                (email, "magic_link"),
            )
            conn.commit()
            db_user_id = int(cur.lastrowid)

    # Ensure the user has a default business + membership (returns int business_id)
    business_id = db_service.get_or_create_single_business_for_user(
        db_user_id, default_name="My Business"
    )

    token = create_access_token(
        {
            "email": email,
            "user_id": db_user_id,      # ✅ INT
            "business_id": business_id, # ✅ INT
        }
    )
    return TokenOut(access_token=token)

# ----------------------------
# AUTH DEPENDENCY (use on your protected endpoints)
# ----------------------------
def get_current_context(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    token = parts[1].strip()
    body = verify_access_token(token)
    return body

@app.get("/me")
def me(ctx: Dict[str, Any] = Depends(get_current_context)):
    email = (ctx.get("email") or "").strip().lower()
    user_id = ctx.get("user_id")

    if not email or not user_id:
        raise HTTPException(status_code=400, detail="Invalid auth context")

    # 1️⃣ Get or create business
    business_id = None

    if hasattr(db_service, "get_or_create_business_for_email"):
        business_id = db_service.get_or_create_business_for_email(email=email)
    else:
        # Fallback logic
        businesses = db_service.list_businesses_for_user(user_id)
        if businesses:
            first = businesses[0]
            business_id = first["id"] if isinstance(first, dict) else first.id
        else:
            business_name = f"{email.split('@')[0]}'s Business"
            business_id = db_service.create_business(business_name)
            db_service.add_membership(user_id, business_id, role="owner")

    # 2️⃣ ENSURE membership exists (THIS WAS MISSING)
    if not db_service.user_has_business_access(user_id, business_id):
        db_service.add_membership(user_id, business_id, role="owner")

    return {
        "email": email,
        "user_id": user_id,
        "business_id": business_id,
    }

UI_ORIGIN = os.getenv("UI_ORIGIN", "http://localhost:8501")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[UI_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "ok", "service": "smallbiz-bookkeeping-engine"}

# =========================
# Business endpoints
# =========================
get_auth_context = get_current_context

def get_current_user_id(ctx=Depends(get_auth_context)) -> int:
    uid = ctx.get("user_id")
    if uid is None:
        raise HTTPException(status_code=401, detail="Missing user_id in token")
    try:
        return int(uid)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid user_id in token")

def get_db_user_id(user_id: int = Depends(get_current_user_id)) -> int:
    return user_id

@app.get("/businesses")
def list_businesses(user_id: int = Depends(get_db_user_id)):
    return db_service.list_businesses_for_user(user_id)


@app.post("/businesses")
def create_business(
    payload: BusinessCreateIn,
    user_id: int = Depends(get_db_user_id),
):
    business_id = db_service.create_business(payload.name)
    db_service.add_membership(user_id, business_id, role="owner")
    return {"id": business_id, "name": payload.name}

BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # project/app/.. -> project
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads"))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
RECEIPTS_DIR = os.path.join(DATA_DIR, "receipts")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RECEIPTS_DIR, exist_ok=True)

BUSINESS_STATE = os.getenv("BUSINESS_STATE", "DE").upper()

# States with no statewide sales tax. (Local taxes can exist in some states; v1 keeps it simple.)
NO_SALES_TAX_STATES = {"DE", "NH", "MT", "OR", "AK"}


# -----------------------------------------------------------------------------
# Small helpers (keep the pipe stable)
# -----------------------------------------------------------------------------

def _dump(obj: Any) -> Any:
    """Pydantic v2 friendly serialization."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return obj


def _safe_int(s: str) -> Optional[int]:
    try:
        return int(s)
    except Exception:
        return None


def _receipt_payload_path(receipt_id: str) -> str:
    # storage_service.save_receipt_payload likely already handles this, but we keep a predictable fallback
    return os.path.join(RECEIPTS_DIR, f"{receipt_id}.json")


def _list_payload_ids() -> List[str]:
    ids: List[str] = []
    if not os.path.exists(RECEIPTS_DIR):
        return ids
    for name in os.listdir(RECEIPTS_DIR):
        if name.endswith(".json"):
            ids.append(name.replace(".json", ""))
    # numeric-ish IDs sort nicely
    ids.sort(key=lambda x: (_safe_int(x) is None, _safe_int(x) or 0, x))
    return ids


def _apply_sales_tax_rules(parsed: Any, ocr_text: str, business_state: str) -> None:
    """
    v1 rule: If business_state is a no-sales-tax state, don't force a tax number.
    Otherwise, leave whatever parser found.
    """
    st = (business_state or "").upper().strip()
    if st in NO_SALES_TAX_STATES:
        # if your ReceiptParsed has .tax, set it to None
        if hasattr(parsed, "tax"):
            parsed.tax = None
        # add a soft flag if the receipt looks like it might include tax text but we ignore it
        if hasattr(parsed, "flags") and isinstance(parsed.flags, list):
            if "NO_SALES_TAX_STATE" not in parsed.flags:
                parsed.flags.append("NO_SALES_TAX_STATE")


def _compute_flags(
    *,
    ocr_status: str,
    normalized: Any,
    parsed: Any,
) -> Tuple[List[str], bool]:
    flags: List[str] = []

       # --- Sanity flags: totals & tax ---
    n_total = getattr(normalized, "total", None)
    n_tax = getattr(normalized, "tax", None)

    if isinstance(n_total, (int, float)) and isinstance(n_tax, (int, float)):
        if n_tax < 0:
            flags.append("TAX_NEGATIVE")
        # Tax should never exceed total
        if n_tax > n_total:
            flags.append("TAX_GT_TOTAL")
            needs_review = True
        # Tax rate sanity (25% is a generous ceiling for most receipts)
        if n_total > 0 and (n_tax / n_total) > 0.25:
            flags.append("TAX_IMPLAUSIBLE_RATE")
            needs_review = True

    # OCR status flags
    s = (ocr_status or "").strip().lower()

    # Only flag hard failures
    if s and s not in ("success", "ok"):
        # Treat low_confidence as a soft warning, not an automatic flag
        if s in ("low_confidence", "low confidence"):
            pass
        else:
            flags.append(f"OCR_{s.upper().replace(' ', '_')}")

    # Missing required-ish fields for bookkeeping v1

     # -----------------------------
    # Confidence-based review rules
    # -----------------------------
    # If we "found" something but confidence is low, force review.
    # This prevents garbage totals on faded / low-quality receipts from slipping through.

    # Pull confidences safely (works whether they live on parsed or normalized)
    total_conf = getattr(normalized, "total_confidence", None)
    date_conf = getattr(normalized, "date_confidence", None)
    vendor_conf = getattr(normalized, "vendor_confidence", None)

    total_reason = (getattr(normalized, "total_reasoning", "") or "").lower()

    # 1) Low total confidence
    if isinstance(total_conf, (int, float)) and total_conf < 80:
        flags.append("LOW_TOTAL_CONFIDENCE")
        needs_review = True

    # 2) Total was chosen from an unlabeled or sketchy context
    # (your parser uses phrases like "unlabeled candidate", "bad context", etc.)
    if any(k in total_reason for k in ("unlabeled", "bad context", "weak label match")):
        flags.append("TOTAL_CONTEXT_WEAK")
        needs_review = True

    # 3) Low date confidence
    if isinstance(date_conf, (int, float)) and date_conf < 70:
        flags.append("LOW_DATE_CONFIDENCE")
        needs_review = True

    # 4) Low vendor confidence (optional, but good for messy receipts)
    if isinstance(vendor_conf, (int, float)) and vendor_conf < 70:
        flags.append("LOW_VENDOR_CONFIDENCE")
        needs_review = True

    # 5) Missing tax isn't always wrong (many states have none),
    # but on "big box" receipts it's often present. If tax missing AND total was weak, review.
    n_tax = getattr(normalized, "tax", None)
    if n_tax is None and ("LOW_TOTAL_CONFIDENCE" in flags or "TOTAL_CONTEXT_WEAK" in flags):
        flags.append("TAX_MISSING_REVIEW")
        needs_review = True

    # We use normalized as the canonical surface, because it's what accountants want.
    n_vendor = getattr(normalized, "vendor", None)
    n_date = getattr(normalized, "date", None)
    n_total = getattr(normalized, "total", None)
    n_category = getattr(normalized, "category", None)

    if not n_vendor:
        flags.append("MISSING_VENDOR")
    if not n_date:
        flags.append("MISSING_DATE")
    if n_total is None:
        flags.append("MISSING_TOTAL")
    if not n_category:
        flags.append("MISSING_CATEGORY")

    # Carry any parser flags forward (but normalize their style)
    p_flags = getattr(parsed, "flags", None)
    if isinstance(p_flags, list):
        for f in p_flags:
            if isinstance(f, str) and f.strip():
                flags.append(f.strip().upper())

    # Deduplicate while preserving order
    seen = set()
    deduped: List[str] = []
    for f in flags:
        if f not in seen:
            seen.add(f)
            deduped.append(f)

    needs_review = len(deduped) > 0
    return deduped, needs_review




def _persist_payload(
    receipt_id: str,
    filename: str,
    saved_path: str,
    ocr_meta: OCRMeta,
    parsed: Any,
    normalized: Any,
    flags: List[str],
    needs_review: bool,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    payload: Dict[str, Any] = {
        "id": str(receipt_id),
        "filename": filename,
        "saved_path": saved_path,
        "ocr": _dump(ocr_meta),
        "parsed": _dump(parsed),
        "normalized": _dump(normalized),
        "flags": flags,
        "needs_review": needs_review,
    }
    if extra:
        payload.update(extra)

    # storage_service is your source of truth; it should save to data/receipts/<id>.json
    saved_json_path = save_receipt_payload(str(receipt_id), filename, payload)
    return saved_json_path


# ---------------------------------------------------------------------------
# TOTALS-ONLY FIX: keep normalized.total aligned with parsed.total
# - Harden against SKU/UPC numbers (e.g., 797860) being treated as totals
# - Only accepts true currency-looking strings (exactly 2 decimals)
# - Rejects 3-decimal “totals” like 797.860
# - Rejects absurd numeric magnitudes that are almost certainly not totals
# ---------------------------------------------------------------------------

import re
from typing import Any, Optional

_MONEY_2DP = re.compile(r"^\s*\$?\d{1,6}(?:,\d{3})*\.\d{2}\s*$")
_SUSPECT_SKU = re.compile(r"\b\d{5,}\b")  # item numbers / SKU / UPC-like


def _coerce_money_float(v: Any) -> Optional[float]:
    """
    Strict money coercion:
    - accepts ints/floats only if they look like plausible receipt totals
    - accepts strings only if they look like currency with EXACTLY 2 decimals
    - rejects 3-decimal artifacts like '797.860' and raw SKUs like '797860'
    """
    try:
        if v is None:
            return None

        # Numeric path
        if isinstance(v, (int, float)):
            f = float(v)

            # Reject absurd totals (very likely SKU/ID leakage)
            # Adjust this ceiling if you truly expect >50k receipts.
            if f < 0 or f >= 50000:
                return None

            # If it's an integer-ish value with lots of digits, reject (SKU/UPC)
            # Example: 797860 -> 797860.0
            if abs(f) >= 10000 and float(int(f)) == f:
                return None

            return f

        # String path
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None

            # Kill obvious SKU/UPC tokens early (no decimals, 5+ digits)
            # If it contains a 5+ digit run and no decimal cents, reject.
            if _SUSPECT_SKU.search(s) and "." not in s:
                return None

            # Remove $ and commas for parsing, but ONLY after strict format check
            if not _MONEY_2DP.match(s):
                return None  # blocks 797.860 and other non-money shapes

            s2 = s.replace("$", "").replace(",", "").strip()
            return float(s2)

        return None
    except Exception:
        return None


def _fix_totals_only(parsed: Any, normalized: Any) -> None:
    """
    ONLY totals: ensure Swagger/UI shows the correct total in normalized (canonical).
    Does not touch vendor/date/category/tax/etc.

    Hardened to prevent SKU/UPC numbers (e.g., 797860) from becoming totals.
    """
    try:
        # pull parsed total (supports dict or object)
        p_total = None
        p_total_conf = None
        p_total_reason = None

        if isinstance(parsed, dict):
            p_total = parsed.get("total")
            p_total_conf = parsed.get("total_confidence")
            p_total_reason = parsed.get("total_reasoning")
            # Optional: if upstream gives you a "source line", we can use it
            p_total_line = parsed.get("total_line") or parsed.get("total_source_line")
            p_ocr_text = parsed.get("ocr_text") or parsed.get("text") or ""
        else:
            p_total = getattr(parsed, "total", None)
            p_total_conf = getattr(parsed, "total_confidence", None)
            p_total_reason = getattr(parsed, "total_reasoning", None)
            p_total_line = getattr(parsed, "total_line", None) or getattr(parsed, "total_source_line", None)
            p_ocr_text = getattr(parsed, "ocr_text", None) or getattr(parsed, "text", None) or ""

        # STRICT money coercion (blocks 797.860 and SKUs)
        p_total_f = _coerce_money_float(p_total)

        # Extra context guard (if we have a source line/text):
        # If the "line" that produced total contains a SKU-like token and does NOT contain "total"/"amount due",
        # reject it.
        src = ""
        if isinstance(p_total_line, str) and p_total_line.strip():
            src = p_total_line.strip()
        elif isinstance(p_ocr_text, str) and p_ocr_text.strip():
            # use small slice to avoid huge scans; this is only a last-resort guard
            src = p_ocr_text[:2000]

        if src:
            low = src.lower()
            has_total_word = any(k in low for k in [" total", "total:", "amount due", "balance", "grand total", "invoice total", "debit", "visa"])
            has_sku = _SUSPECT_SKU.search(src) is not None
            # If it looks like a line item (SKU present) and doesn't explicitly look like a total line, reject
            if has_sku and not has_total_word:
                p_total_f = None

        # If normalized.total is missing, copy parsed.total into it (ONLY if valid)
        n_total = getattr(normalized, "total", None)
        if n_total is None and p_total_f is not None:
            setattr(normalized, "total", round(p_total_f, 2))

        # Optionally mirror total confidence/reasoning into normalized if missing there
        # (still totals-only; helps Swagger/debug)
        if getattr(normalized, "total_confidence", 0.0) in (0, 0.0) and p_total_conf is not None:
            try:
                setattr(normalized, "total_confidence", float(p_total_conf) or 0.0)
            except Exception:
                pass

        if (getattr(normalized, "total_reasoning", "") or "") == "" and p_total_reason:
            try:
                setattr(normalized, "total_reasoning", str(p_total_reason))
            except Exception:
                pass

        # Keep parsed dict clean too (if it exists) so response "parsed.total" isn't weird
        if isinstance(parsed, dict) and parsed.get("total") is None and getattr(normalized, "total", None) is not None:
            parsed["total"] = getattr(normalized, "total", None)

    except Exception:
        # totals fix should never crash the pipeline
        return


# ---------------------------------------------------------------------------
# Backwards-compatible alias if other parts of your code call _coerce_float(...)
# Keep this BELOW the hardened functions so it uses the strict money coercion.
# ---------------------------------------------------------------------------

def _coerce_float(v: Any) -> Optional[float]:
    return _coerce_money_float(v)


def _process_one(
    *,
    file_path: str,
    filename: str,
    explanation: Optional[str],
    business_type: Optional[str],
    business_state: str,
    business_id: int,
) -> UploadResponse:
    # --- OCR ---
    text, ocr_status, ocr_source, ocr_confidence = extract_text(file_path)

    ocr_meta = OCRMeta(
        ocr_text=text or "",
        ocr_status=ocr_status or "unknown",
        ocr_source=ocr_source or "unknown",
        ocr_confidence=float(ocr_confidence or 0.0),
    )

    # --- Parse ---
    parsed = parse_receipt(text or "")

    # Make sure form fields actually show up in the response payload
# (parser returns parsed fields; main.py must attach request context fields)
    if isinstance(parsed, dict):
        parsed["explanation"] = explanation
        parsed["business_type"] = business_type
        parsed["business_state"] = business_state
    else:
        # if you ever switch back to an object model
        if hasattr(parsed, "explanation"):
            parsed.explanation = explanation
        if hasattr(parsed, "business_type"):
            parsed.business_type = business_type
        if hasattr(parsed, "business_state"):
            parsed.business_state = business_state

    # Attach explanation/business_type if your ReceiptParsed supports it
    if is_dataclass(parsed):
        parsed = asdict(parsed)
    elif hasattr(parsed, "__dict__") and not isinstance(parsed, dict):
        parsed = dict(parsed.__dict__)

 # --- Category (optional) ---
    # Prioritize explanation when possible (your earlier design decision)
    if categorize_purchase is not None:
        # parsed is a dict by this point in your code, so getattr() was always failing
        vendor_for_cat = parsed.get("vendor") if isinstance(parsed, dict) else getattr(parsed, "vendor", None)

        category_input_text = explanation.strip() if explanation else (text or "")
        try:
            cat = categorize_purchase(
                vendor=vendor_for_cat,
                ocr_text=category_input_text,
                explanation=explanation,
                business_type=business_type
            )
            # expect: {"category": str|None, "confidence": float, "reasoning": str}

            # Initialize parsed attributes if they don't exist (for dict)
            if isinstance(parsed, dict):
                if not hasattr(parsed, "category"):
                    parsed.setdefault("category", None)
                if not hasattr(parsed, "category_confidence"):
                    parsed.setdefault("category_confidence", None)
                if not hasattr(parsed, "category_reasoning"):
                    parsed.setdefault("category_reasoning", None)
                if not hasattr(parsed, "flags"):
                    parsed.setdefault("flags", [])
                if not hasattr(parsed, "needs_review"):
                    parsed.setdefault("needs_review", False)
            else:
                # If parsed is a dataclass
                if not hasattr(parsed, "category"):
                    parsed.category = None
                if not hasattr(parsed, "category_confidence"):
                    parsed.category_confidence = None
                if not hasattr(parsed, "category_reasoning"):
                    parsed.category_reasoning = None
                if not hasattr(parsed, "flags"):
                    parsed.flags = []
                if not hasattr(parsed, "needs_review"):
                    parsed.needs_review = False

            if isinstance(cat, dict):
                if isinstance(parsed, dict):
                    parsed["category"] = cat.get("category")
                    parsed["category_confidence"] = float(cat.get("confidence") or 0.0)
                    parsed["category_reasoning"] = cat.get("reasoning") or ""
                    if (cat.get("category") is None) and isinstance(parsed.get("flags"), list):
                        parsed["flags"].append("MISSING_CATEGORY")
                    if (cat.get("category") is None):
                        parsed["needs_review"] = True
                else:
                    if hasattr(parsed, "category"):
                        parsed.category = cat.get("category")
                    if hasattr(parsed, "category_confidence"):
                        parsed.category_confidence = float(cat.get("confidence") or 0.0)
                    if hasattr(parsed, "category_reasoning"):
                        parsed.category_reasoning = cat.get("reasoning") or ""
                    if (cat.get("category") is None) and hasattr(parsed, "flags") and isinstance(parsed.get("flags"), list):
                        parsed.flags.append("MISSING_CATEGORY")
                    if (cat.get("category") is None) and hasattr(parsed, "needs_review"):
                        parsed.needs_review = True

        except Exception:
            # category is helpful, not mission-critical; don't 500
            if isinstance(parsed, dict):
                parsed.setdefault("flags", [])
                if "CATEGORY_ENGINE_ERROR" not in parsed["flags"]:
                    parsed["flags"].append("CATEGORY_ENGINE_ERROR")
            else:
                if hasattr(parsed, "flags") and isinstance(parsed.flags, list):
                    parsed.flags.append("CATEGORY_ENGINE_ERROR")

    # --- Tax rules ---
    _apply_sales_tax_rules(parsed, text or "", business_state)

    # --- Normalize ---
    normalized_dict_or_model = normalize_receipt(parsed)
    if isinstance(normalized_dict_or_model, dict):
        normalized = ReceiptNormalized(**normalized_dict_or_model)
    else:
        normalized = normalized_dict_or_model

    # --- TOTALS-ONLY FIX (Swagger) ---
    _fix_totals_only(parsed, normalized)

    # --- Flags / needs_review ---
    flags, needs_review = _compute_flags(
        ocr_status=ocr_meta.ocr_status,
        normalized=normalized,
        parsed=parsed,
    )

    # Ensure normalized carries review state (if your schema expects it there too)
    if hasattr(normalized, "needs_review"):
        normalized.needs_review = needs_review
    if hasattr(normalized, "flags"):
        normalized.flags = flags
    if hasattr(normalized, "explanation"):
        normalized.explanation = explanation
    if hasattr(normalized, "business_type"):
        normalized.business_type = business_type
    if hasattr(normalized, "business_state"):
        normalized.business_state = business_state

    # --- ID + persist ---
    # If DB is available, use it. Otherwise, UUID.
    if db_service is not None:
        try:
            receipt_id = db_service.insert_receipt(
                parsed=_dump(parsed),
                source_filename=filename,
                saved_json_path="",  # set after saving payload
                business_id=business_id,
            )
            receipt_id = str(receipt_id)
        except Exception:
            receipt_id = str(uuid4())
    else:
        receipt_id = str(uuid4())

    saved_json_path = _persist_payload(
        receipt_id=receipt_id,
        filename=filename,
        saved_path=file_path,
        ocr_meta=ocr_meta,
        parsed=parsed,
        normalized=normalized,
        flags=flags,
        needs_review=needs_review,
        extra={
            "business_type": business_type,
            "business_state": business_state,
            "explanation": explanation,
        },
    )

    return UploadResponse(
        id=str(receipt_id),
        filename=filename,
        saved_path=saved_json_path,
        ocr=ocr_meta,
        parsed=parsed,
        normalized=normalized,
        flags=flags,
        needs_review=needs_review,
    )

# -----------------------------------------------------------------------------# Endpoints
# -----------------------------------------------------------------------------

# ----------------------------
# Business scoping dependency
# ----------------------------
def _id_to_int(x: Any) -> Optional[int]:
    """
    Accept:
      - int / numeric strings
      - hex strings like 'a05daf223277'
      - token-style ids like 'biz_a05daf223277' or 'usr_a05daf223277'
    Return an int or None.
    """
    if x is None:
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, (float,)):
        return int(x)

    s = str(x).strip()
    if not s:
        return None

    # strip known prefixes
    for p in ("biz_", "usr_"):
        if s.lower().startswith(p):
            s = s[len(p):].strip()

    # digits-only -> int base10
    if s.isdigit():
        try:
            return int(s)
        except Exception:
            return None

    # hex -> int base16
    try:
        return int(s, 16)
    except Exception:
        return None


def get_current_user_id(ctx: Dict[str, Any] = Depends(get_auth_context)) -> int:
    """
    Your token currently stores user_id like 'usr_a05daf...'.
    Convert it to an INT for DB access checks.
    """
    uid = _id_to_int(ctx.get("user_id"))
    if uid is None:
        raise HTTPException(status_code=401, detail="Invalid user_id in token")
    return uid


def require_business_access(*, user_id: int, business_id: int, ctx: Dict[str, Any]) -> None:
    """
    First allow if the requested business_id matches the token business_id (same session).
    Then (if available) enforce DB membership.
    """
    token_biz = _id_to_int(ctx.get("business_id"))
    if token_biz is not None and int(business_id) == int(token_biz):
        return

    if not hasattr(db_service, "user_has_business_access"):
        # If DB access checks aren't implemented yet, don't hard-block uploads.
        return

    ok = db_service.user_has_business_access(int(user_id), int(business_id))
    if not ok:
        raise HTTPException(status_code=403, detail="No access to this business")


def get_scoped_business_id(
    ctx: Dict[str, Any] = Depends(get_auth_context),
    user_id: int = Depends(get_current_user_id),
    business_id: Optional[str] = Header(None, alias="X-Business-Id"),
) -> int:
    """
    Require Authorization.
    X-Business-Id is optional:
      - if omitted, uses token business_id
      - if provided, accepts int, hex, or 'biz_<hex>'
    """
    # pick header first, else token
    raw = business_id if business_id is not None else ctx.get("business_id")
    bid = _id_to_int(raw)
    if bid is None:
        raise HTTPException(status_code=400, detail="X-Business-Id must be an integer (or hex / biz_<hex>).")

    require_business_access(user_id=user_id, business_id=bid, ctx=ctx)
    return int(bid)


# --- /upload ---
# NOTE:
# - UI sends multipart with repeated field name "files"
# - Some older camera paths may send a single field name "file"
# This block supports BOTH and always returns a BatchUploadResponse shape.

@app.post("/upload", response_model=BatchUploadResponse)
async def upload(
    # UI-aligned: ("files", (...)) repeated
    files: Optional[List[UploadFile]] = File(None),
    # Back-compat: single file field "file"
    file: Optional[UploadFile] = File(None),
    explanation: Optional[str] = Form(None),
    business_type: Optional[str] = Form(None),
    business_name: Optional[str] = Form(None),  # alias support from UI
    business_state: Optional[str] = Form(None),
    business_id: int = Depends(get_scoped_business_id),  # must tolerate missing header in its own logic
):
    # Normalize inputs: accept either "files" or "file"
    upload_files: List[UploadFile] = []
    if files:
        upload_files.extend(files)
    if file:
        upload_files.append(file)

    if not upload_files:
        raise HTTPException(status_code=400, detail="No files provided. Send multipart field 'files' (or 'file').")

    bs = (business_state or BUSINESS_STATE).upper().strip()
    bt = (business_type or business_name)  # keep your existing behavior

    batch_id = str(uuid4())
    results: List[BatchUploadResult] = []
    processed = 0

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    for uf in upload_files:
        try:
            if not uf or not uf.filename:
                raise ValueError("Missing filename")

            file_path = os.path.join(UPLOAD_DIR, uf.filename)
            contents = await uf.read()
            with open(file_path, "wb") as f:
                f.write(contents)

            # Your existing pipeline function
            resp = _process_one(
                file_path=file_path,
                filename=uf.filename,
                explanation=explanation,
                business_type=bt,
                business_state=bs,
                business_id=business_id,
            )

            results.append(
                BatchUploadResult(
                    filename=uf.filename,
                    receipt_id=getattr(resp, "id", None),
                    status="success",
                    error=None,
                    ocr=getattr(resp, "ocr", None),
                    flags=getattr(resp, "flags", []),
                    needs_review=getattr(resp, "needs_review", True),
                    parsed=getattr(resp, "parsed", None),
                    normalized=getattr(resp, "normalized", None),
                )
            )
            processed += 1

        except Exception as e:
            results.append(
                BatchUploadResult(
                    filename=getattr(uf, "filename", "unknown"),
                    receipt_id=None,
                    status="failed",
                    error=f"{type(e).__name__}: {e}",
                    ocr=None,
                    flags=[],
                    needs_review=True,
                    parsed=None,
                    normalized=None,
                )
            )

    return BatchUploadResponse(
        batch_id=batch_id,
        total=len(upload_files),
        processed=processed,
        results=results,
    )


# Keep /upload/batch as an alias so older UI paths still work
@app.post("/upload/batch", response_model=BatchUploadResponse)
async def upload_batch(
    files: List[UploadFile] = File(...),
    business_type: Optional[str] = Form(None),
    business_name: Optional[str] = Form(None),
    business_state: Optional[str] = Form(None),
    explanation: Optional[str] = Form(None),
    business_id: int = Depends(get_scoped_business_id),
):
    # Reuse the exact same implementation
    return await upload(
        files=files,
        file=None,
        explanation=explanation,
        business_type=business_type,
        business_name=business_name,
        business_state=business_state,
        business_id=business_id,
    )

router = APIRouter()

# ----------------------------
# UI-safe receipts endpoints
# ----------------------------

def _safe_json(val: Any) -> Dict[str, Any]:
    """Convert dict/JSON-string/None into a dict. Never returns a raw string."""
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    if isinstance(val, (bytes, bytearray)):
        val = val.decode("utf-8", errors="ignore")
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
            return parsed if isinstance(parsed, dict) else {"_raw": parsed}
        except Exception:
            return {"_raw": s}
    return {"_raw": str(val)}

def _to_dict(row: Any) -> Dict[str, Any]:
    """SQLite row / tuple / dict -> dict (best effort)."""
    if isinstance(row, dict):
        return row
    try:
        return dict(row)
    except Exception:
        return {"_raw": row}

def _coerce_bool(x: Any) -> Optional[bool]:
    if x is None:
        return None
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return bool(x)
    if isinstance(x, str):
        s = x.strip().lower()
        if s in ("1", "true", "yes", "y", "t"):
            return True
        if s in ("0", "false", "no", "n", "f"):
            return False
    return None

def _coerce_flags(flags: Any) -> List[str]:
    if flags is None:
        return []
    if isinstance(flags, list):
        return [str(x) for x in flags]
    if isinstance(flags, str):
        s = flags.strip()
        if not s:
            return []
        # might be JSON list string
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except Exception:
            pass
        # fallback: comma-separated
        return [p.strip() for p in s.split(",") if p.strip()]
    return [str(flags)]

def _extract_normalized(r: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize all the possible shapes you store:
    - db row columns (vendor/date/total/etc)
    - payload_json (string) that contains {"normalized": {...}} or {"parsed": {"normalized": {...}}}
    - stored JSON files
    """
    payload = _safe_json(
        r.get("payload")
        or r.get("payload_json")
        or r.get("json")
        or r.get("data")
    )

    # normalized may be nested in different places
    normalized = (
        _safe_json(r.get("normalized"))
        or _safe_json(payload.get("normalized"))
        or _safe_json((payload.get("parsed") or {}).get("normalized"))
    )

    # Merge direct db columns into normalized if missing
    for k in [
        "vendor", "vendor_confidence",
        "date", "date_confidence",
        "total", "total_confidence",
        "tax", "category",
        "error", "image_path", "file_path", "filename",
        "status", "exported_at", "archived_at",
    ]:
        if normalized.get(k) is None and r.get(k) is not None:
            normalized[k] = r.get(k)

    # flags + needs_review are the most important for UI
    flags = normalized.get("flags")
    if flags is None:
        flags = r.get("flags") or payload.get("flags")
    normalized["flags"] = _coerce_flags(flags)

    nr = normalized.get("needs_review")
    if nr is None:
        nr = r.get("needs_review") or payload.get("needs_review")
    nr_bool = _coerce_bool(nr)
    normalized["needs_review"] = bool(nr_bool) if nr_bool is not None else False

    return normalized

def _load_rows_from_db(limit: int, business_id: int, status: str = "active") -> List[Any]:
    """
    DB-first (recommended). Now scoped to business_id + status.
    """
    try:
        if hasattr(db_service, "list_receipts"):
            return db_service.list_receipts(limit=limit, business_id=business_id, status=status)
    except Exception:
        pass
    return []

def _load_rows_from_files(limit: int, business_id: int) -> List[Dict[str, Any]]:
    """
    File fallback (scoped): ONLY look in a business folder to avoid cross-business leaks.
    You should export your payload JSONs into: data/receipts/<business_id>/
    """
    candidates = [
        Path("data/receipts") / str(business_id),
        Path("data") / "receipts" / str(business_id),
    ]
    rows: List[Dict[str, Any]] = []
    for base in candidates:
        if not base.exists():
            continue
        json_files = sorted(base.glob("*.json"))
        for p in json_files:
            try:
                rows.append(json.loads(p.read_text(encoding="utf-8")))
                if len(rows) >= limit:
                    return rows
            except Exception:
                continue
        if rows:
            return rows
    return rows

@app.get("/receipts")
def get_receipts(
    limit: int = 500,
    needs_review: Optional[bool] = None,
    status: str = "active",  # active | archived | all
    business_id: Optional[int] = Header(None, alias="X-Business-Id"),
) -> List[Dict[str, Any]]:
    """
    Returns a LIST OF DICTS (never strings) for Streamlit consumption.
    Business-scoped, but header is OPTIONAL.
    """


        # ---- load receipts ----
    rows = _load_rows_from_db(
        limit=limit,
        business_id=business_id,
        status=status,
    )

    # fallback to file-based receipts if DB empty
    if not rows:
        rows = _load_rows_from_files(
            limit=limit,
            business_id=business_id,
        )

    results: List[Dict[str, Any]] = []

    for row in rows:
        r = _to_dict(row)
        normalized = _extract_normalized(r)

        out: Dict[str, Any] = {
            "receipt_id": (
                r.get("id")
                or r.get("receipt_id")
                or normalized.get("receipt_id")
            ),
            "filename": (
                r.get("filename")
                or normalized.get("filename")
                or r.get("file_name")
            ),
            "status": (
                r.get("status")
                or normalized.get("status")
                or "active"
            ),
            "exported_at": (
                r.get("exported_at")
                or normalized.get("exported_at")
            ),
            "archived_at": (
                r.get("archived_at")
                or normalized.get("archived_at")
            ),
            "normalized": normalized,
        }

        # expose common normalized fields at top-level for UI filtering/sorting
        for k in [
            "vendor",
            "total",
            "date",
            "category",
            "vendor_confidence",
            "date_confidence",
            "total_confidence",
            "category_confidence",
            "needs_review",
        ]:
            if k in normalized:
                out[k] = normalized[k]

        results.append(out)

    # ---- UI-level needs_review filter (SAFE, no DB changes) ----
    if needs_review is not None:
        results = [
            r for r in results
            if bool(r.get("needs_review")) == needs_review
        ]

    return results

@app.get("/review/queue")
def get_review_queue(
    limit: int = 500,
    business_id: int = Depends(get_scoped_business_id),  # ✅ AUTH + BUSINESS LOCK
) -> List[Dict[str, Any]]:
    # DB-backed review queue, scoped
    try:
        rows = db_service.list_review_queue(limit=limit, business_id=business_id)
        # reuse the same UI normalization shape
        results: List[Dict[str, Any]] = []
        for row in rows:
            r = _to_dict(row)
            normalized = _extract_normalized(r)
            out: Dict[str, Any] = {
                "receipt_id": r.get("id") or r.get("receipt_id") or normalized.get("receipt_id"),
                "filename": r.get("filename") or normalized.get("filename") or r.get("file_name"),
                "status": r.get("status") or normalized.get("status") or "active",
                "normalized": normalized,
            }
            for k in [
                "vendor","vendor_confidence",
                "date","date_confidence",
                "total","total_confidence",
                "tax","category",
                "needs_review","flags","error",
                "image_path","file_path"
            ]:
                out[k] = normalized.get(k)
            results.append(out)
        return results
    except Exception:
        # fallback: derive from /receipts?needs_review=true (still scoped)
        return get_receipts(limit=limit, needs_review=True, status="active", business_id=business_id)

@app.get("/receipts/{receipt_id}", response_model=UploadResponse)
def get_receipt(
    receipt_id: str,
    business_id: int = Depends(get_scoped_business_id),  # ✅ AUTH + BUSINESS LOCK
):
    """
    Loads the canonical saved payload and rehydrates the UploadResponse.
    Business lock is enforced by DB ownership check.
    """
    # Enforce business ownership at DB layer
    try:
        rid_int = int(receipt_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid receipt_id")

    if not db_service.get_receipt_row(rid_int, business_id=business_id):
        raise HTTPException(status_code=404, detail="Receipt not found")

    try:
        payload = load_receipt_payload(receipt_id)
        if not payload:
            raise FileNotFoundError(f"receipt_id {receipt_id} not found")

        o = payload.get("ocr") or {}
        ocr_meta = OCRMeta(
            ocr_text=o.get("ocr_text") or "",
            ocr_status=o.get("ocr_status") or "unknown",
            ocr_source=o.get("ocr_source") or "unknown",
            ocr_confidence=float(o.get("ocr_confidence") or 0.0),
        )

        return UploadResponse(
            id=str(payload.get("id") or receipt_id),
            filename=payload.get("filename") or "",
            saved_path=payload.get("saved_path") or _receipt_payload_path(receipt_id),
            ocr=ocr_meta,
            parsed=payload.get("parsed"),
            normalized=payload.get("normalized"),
            flags=payload.get("flags") or [],
            needs_review=bool(payload.get("needs_review") or False),
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Receipt not found: {type(e).__name__}: {e}")

@app.patch("/receipts/{receipt_id}/review", response_model=UploadResponse)
def patch_receipt_review(
    receipt_id: str,
    patch: ReceiptReviewPatch,
    business_id: int = Depends(get_scoped_business_id),  # ✅ AUTH + BUSINESS LOCK
):
    """
    Accountant review endpoint:
    - Only updates fields provided
    - Recomputes flags/needs_review afterwards
    - Persists back to canonical payload
    - Updates DB searchable fields (scoped to business)
    """
    # Enforce business ownership at DB layer
    try:
        rid_int = int(receipt_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid receipt_id")

    if not db_service.get_receipt_row(rid_int, business_id=business_id):
        raise HTTPException(status_code=404, detail="Receipt not found")

    payload = load_receipt_payload(receipt_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Receipt not found")

    parsed = payload.get("parsed") or {}
    normalized = payload.get("normalized") or {}

    patch_dict = _dump(patch) if patch is not None else {}
    for k, v in patch_dict.items():
        if v is None:
            continue
        if isinstance(normalized, dict):
            normalized[k] = v
        else:
            if hasattr(normalized, k):
                setattr(normalized, k, v)

        if isinstance(parsed, dict):
            parsed[k] = v
        else:
            if hasattr(parsed, k):
                setattr(parsed, k, v)

    ocr = payload.get("ocr") or {}
    ocr_status = ocr.get("ocr_status") or "unknown"

    if isinstance(normalized, dict):
        normalized_obj = ReceiptNormalized(**normalized)
    else:
        normalized_obj = normalized

    class _ParsedShim:
        def __init__(self, d: Dict[str, Any]):
            self.flags = d.get("flags") if isinstance(d.get("flags"), list) else []
    parsed_for_flags = parsed if not isinstance(parsed, dict) else _ParsedShim(parsed)

    flags, needs_review = _compute_flags(
        ocr_status=ocr_status,
        normalized=normalized_obj,
        parsed=parsed_for_flags,
    )

    payload["parsed"] = _dump(parsed)
    payload["normalized"] = _dump(normalized_obj)
    payload["flags"] = flags
    payload["needs_review"] = needs_review

    save_receipt_payload(str(receipt_id), payload.get("filename") or "", payload)

    # ✅ Update DB searchable fields (scoped)
    try:
        db_service.update_receipt_review_fields(
            rid_int,
            business_id=business_id,
            vendor=(patch_dict.get("vendor") if isinstance(patch_dict, dict) else None),
            date=(patch_dict.get("date") if isinstance(patch_dict, dict) else None),
            total=(patch_dict.get("total") if isinstance(patch_dict, dict) else None),
            category=(patch_dict.get("category") if isinstance(patch_dict, dict) else None),
            needs_review=needs_review,
            flags=flags,
        )
    except Exception:
        # keep file-backed response working even if DB update fails
        pass

    ocr_meta = OCRMeta(
        ocr_text=ocr.get("ocr_text") or "",
        ocr_status=ocr_status,
        ocr_source=ocr.get("ocr_source") or "unknown",
        ocr_confidence=float(ocr.get("ocr_confidence") or 0.0),
    )

    return UploadResponse(
        id=str(payload.get("id") or receipt_id),
        filename=payload.get("filename") or "",
        saved_path=payload.get("saved_path") or _receipt_payload_path(receipt_id),
        ocr=ocr_meta,
        parsed=payload.get("parsed"),
        normalized=payload.get("normalized"),
        flags=flags,
        needs_review=needs_review,
    )


# ----------------------------
# Archive / Export (clean)
# ----------------------------
class ArchiveRequest(BaseModel):
    receipt_ids: List[int]
    mark_exported: bool = True  # if True, also sets exported_at


@app.post("/receipts/archive")
def archive_receipts_endpoint(
    payload: ArchiveRequest,
    business_id: int = Depends(get_scoped_business_id),  # ✅ AUTH + BUSINESS LOCK
):
    updated = db_service.archive_receipts(
        receipt_ids=payload.receipt_ids,
        business_id=business_id,
        mark_exported=bool(payload.mark_exported),
    )
    return {"archived": int(updated)}