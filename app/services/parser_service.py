# app/services/parser_service.py
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple, Any

from app.schemas import ReceiptParsed

# -----------------------------------------------------------------------------
# CPA-grade parsing philosophy (v1):
# - OCR is noisy; parse defensively
# - Extract MANY candidates for each field
# - Score with context: labels, proximity, position, plausibility, conflicts
# - Return best + confidence + reasoning + source
# - Never crash; always return a ReceiptParsed + flags
#
# This parser is designed to work with your OCR output, including:
# - merged multipass blobs
# - "----- VENDOR PASS -----" and "----- TOTALS PASS -----" sections
# - PDFs (text extracted or OCR’d)
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
# Vendor knowledge (expand over time via review feedback)
# - Keep canonical names stable (accounting exports prefer stable vendors)
# -----------------------------------------------------------------------------

VENDOR_ALIASES: Dict[str, List[str]] = {
    "Walmart": ["walmart", "wal-mart", "wal mart", "walmrt", "wm supercenter", "wm"],
    "Target": ["target", "tgt"],
    "Amazon": ["amazon", "amazon.com", "amzn", "amzn mktp", "amzn marketplace"],
    "Costco": ["costco", "costco wholesale"],
    "Home Depot": ["home depot", "the home depot", "homedepot", "home dep0t", "home-depot"],
    "Lowe's": ["lowe's", "lowes", "lowe s"],
    "AutoZone": ["autozone", "auto zone", "autozo", "auto z0ne"],
    "O'Reilly Auto Parts": ["o'reilly", "oreilly", "o reilly", "oreilly auto", "o'reilly auto"],
    "Advance Auto Parts": ["advance auto", "advanceautoparts", "advance auto parts", "adv auto"],
    "CVS": ["cvs", "cvs/pharmacy", "cvs pharmacy"],
    "Walgreens": ["walgreens", "walgreeens", "walgreen"],
    "Dollar General": ["dollar general", "dollargeneral", "dg"],
    "Shell": ["shell"],
    "Exxon": ["exxon", "esso"],
    "Chevron": ["chevron"],
    "Sunoco": ["sunoco"],
    "BP": ["bp", "b p"],
    "7-Eleven": ["7-eleven", "7 eleven", "seven eleven"],
    "Starbucks": ["starbucks", "sbux"],
    "McDonald's": ["mcdonalds", "mc donalds", "mc donald's", "mcd"],
}

# Common "total" labels (ordered strongest -> weaker)
TOTAL_LABELS = [
    "total",
    "sale total",
    "grand total",
    "invoice total",
    "total due",
    "order total",
]

SUBTOTAL_LABELS = ["subtotal", "sub total"]
TAX_LABELS = ["sales tax", "tax", "vat", "gst", "hst"]
DATE_LABELS = ["date", "dated", "txn date", "trans date", "transaction date", "purchase date", "issued", "invoice date"]

# Money-adjacent labels that are NOT totals (penalize)
NON_TOTAL_HINTS = [
    "subtotal", "sub total",
    "tip",
    "cash",
    "change",
    "discount", "coupon", "savings",
    "amount tendered", "tender",
    "auth", "approval",
    "points", "rewards",
    "balance",  # balance can mean many things; keep but weak
]

# OCR text section headers (from your OCR multipass)
SECTION_VENDOR = "----- VENDOR PASS"
SECTION_TOTALS = "----- TOTALS PASS"
SECTION_NUMERIC = "----- NUMERIC PASS"
SECTION_SOFTTEXT = "----- SOFT TEXT PASS"

# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

def _apply_parser_flags(parsed: Any, text: str) -> None:
    """
    Minimal no-crash flag hook.
    Keeps your pipeline stable even if your flag system is in flux.
    """
    if not hasattr(parsed, "flags") or parsed.flags is None:
        parsed.flags = []
    if not hasattr(parsed, "needs_review") or parsed.needs_review is None:
        parsed.needs_review = False

    # Basic examples (optional)
    # If total missing, flag it
    if getattr(parsed, "total", None) in (None, 0, 0.0):
        parsed.flags.append("TOTAL_MISSING")
        parsed.needs_review = True

def parse_receipt(ocr_text: str) -> ReceiptParsed:
    """
    Main API called by your pipeline.
    Never raises.
    """
    parsed = ReceiptParsed()
    try:
        text = _normalize_text(ocr_text or "")
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        joined = "\n".join(lines)

        # Split text into logical sections (helps vendor & totals)
        sections = _split_sections(lines)

        # Vendor
        v_name, v_conf, v_reason, v_src = _extract_vendor(lines, sections)
        parsed.vendor = v_name
        parsed.vendor_confidence = v_conf
        parsed.vendor_reasoning = v_reason
        parsed.vendor_source = v_src

        # Date
        d_val, d_conf, d_reason = _extract_date(lines, joined, sections)
        parsed.date = d_val
        parsed.date_confidence = d_conf
        parsed.date_reasoning = d_reason

        # Tax
        tax_val, tax_conf, tax_reason = _extract_tax(lines, joined, sections)
        parsed.tax = tax_val
        if tax_conf > 0:
            parsed.extra["tax_confidence"] = tax_conf
            parsed.extra["tax_reasoning"] = tax_reason

        # Total
        t_val, t_conf, t_reason = _extract_total(lines, joined, sections, tax_val)
        parsed.total = t_val
        parsed.total_confidence = t_conf
        parsed.total_reasoning = t_reason

        # Soft flags
        _apply_parser_flags(parsed, text)

        return parsed

    except Exception as e:
        # Never break the API.
        parsed.flags = parsed.flags or []
        parsed.flags.append(f"PARSER_EXCEPTION_{type(e).__name__}".upper())
        parsed.needs_review = True
        return parsed


# -----------------------------------------------------------------------------
# Normalization + basic helpers
# -----------------------------------------------------------------------------

def _normalize_text(t: str) -> str:
    if not t:
        return ""
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    # keep printable + newline/tab
    t = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", "", t)
    out: List[str] = []
    for ln in t.split("\n"):
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln:
            out.append(ln)
    return "\n".join(out).strip()


def _clamp01(x: float) -> float:
    if x < 0:
        return 0.0
    if x > 1:
        return 1.0
    return x


def _to_conf_100(x01: float) -> float:
    return round(_clamp01(x01) * 100.0, 1)


def _safe_float(s: str) -> Optional[float]:
    try:
        return float(s)
    except Exception:
        return None


def _line_has_any(line: str, needles: List[str]) -> bool:
    lo = (line or "").lower()
    return any(n in lo for n in needles)


def _best_line_window(lines: List[str], idx: int, radius: int = 2) -> str:
    start = max(0, idx - radius)
    end = min(len(lines), idx + radius + 1)
    return " | ".join(lines[start:end])


def _strip_noise(s: str) -> str:
    # Remove common OCR junk but preserve useful punctuation
    return re.sub(r"[^A-Za-z0-9 '&\.\-\/]", " ", s).strip()


def _collapse_spaces(s: str) -> str:
    return re.sub(r"\s{2,}", " ", (s or "").strip())


# -----------------------------------------------------------------------------
# Sections: useful because your OCR now merges multiple passes
# -----------------------------------------------------------------------------

def _split_sections(lines: List[str]) -> Dict[str, List[str]]:
    """
    Splits OCR output into sections based on headers.
    Returns dict(section_name -> lines).
    Always includes "full".
    """
    out: Dict[str, List[str]] = {"full": list(lines)}
    current = "full"

    for ln in lines:
        up = ln.upper()
        if "-----" in ln and "PASS" in up:
            if "VENDOR" in up:
                current = "vendor_pass"
                out.setdefault(current, [])
                continue
            if "TOTAL" in up:
                current = "totals_pass"
                out.setdefault(current, [])
                continue
            if "NUMERIC" in up:
                current = "numeric_pass"
                out.setdefault(current, [])
                continue
            if "SOFT TEXT" in up or "SOFTTEXT" in up:
                current = "softtext_pass"
                out.setdefault(current, [])
                continue
            # unknown pass header
            current = "other_pass"
            out.setdefault(current, [])
            continue

        out.setdefault(current, []).append(ln)

    return out


# -----------------------------------------------------------------------------
# Money parsing (BEST EFFORT, OCR-aware)
# -----------------------------------------------------------------------------

def _money_candidates_from_text(text: str) -> List[Tuple[float, str, int]]:
    """
    Money candidate extractor for noisy OCR.

    Returns list of (value, raw, position_index).

    Handles:
      - $12.34, 12.34, 1,234.56
      - European decimal: 12,34 -> 12.34
      - Truncated decimals: 47.4 -> 47.40
      - Optional implied-cents integers: 4749 -> 47.49 (guarded by heuristics)

    Avoids:
      - dates like 01/27/2026
      - phone numbers / long IDs
      - obvious non-money integers unless receipt context suggests cents
    """
    if not text:
        return []

    out: List[Tuple[float, str, int]] = []

    # Normalize spacing but keep original for positions
    t = text

    def _add(val: float, raw: str, pos: int) -> None:
        try:
            if val <= 0 or val > 50000:
                return
            out.append((round(float(val), 2), raw.strip(), int(pos)))
        except Exception:
            return

    # --- 1) Strong: explicit decimal with dot: 12.34 / 1,234.56 / $12.34 ---
    dec_pat = re.compile(r"(?P<prefix>\$)?\s*(?P<num>(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2})")
    for m in dec_pat.finditer(t):
        raw = m.group(0)
        num = (m.group("num") or "").replace(",", "")
        val = _safe_float(num)
        if val is None:
            continue
        _add(val, raw, m.start())

    # --- 2) Strong: explicit decimal with comma: 12,34 / 1.234,56 (OCR/Euro-ish) ---
    # Keep this conservative: only treat comma as decimal when followed by exactly 2 digits.
    euro_pat = re.compile(r"(?P<prefix>\$)?\s*(?P<num>\d{1,6},\d{2})\b")
    for m in euro_pat.finditer(t):
        raw = m.group(0)
        num = (m.group("num") or "")
        # skip if it's clearly a thousands separator style like 1,234 (no decimals)
        if re.search(r"\d{1,3},\d{3}\b", num):
            continue
        num = num.replace(",", ".")
        val = _safe_float(num)
        if val is None:
            continue
        _add(val, raw, m.start())

    # --- 3) Medium: truncated decimal: 47.4 -> 47.40 / $7.5 -> 7.50 ---
    trunc_pat = re.compile(r"(?P<prefix>\$)?\s*(?P<num>\d{1,6}\.\d)\b")
    for m in trunc_pat.finditer(t):
        raw = m.group(0)
        num = (m.group("num") or "")
        val = _safe_float(num)
        if val is None:
            continue
        _add(round(val, 2), raw, m.start())

    # --- 4) Guarded: implied cents integers: 4749 -> 47.49 ---
    # Only enable when nearby text screams "receipt totals".
    # This avoids misreading phones, AID, approval codes, etc.
    lo = t.lower()
    receipt_money_context = any(k in lo for k in [
        "total", "sale total", "grand total", "amount due", "balance due",
        "subtotal", "tax", "vat", "gst", "hst", "order total",
    ])

    # Penalize contexts that are usually IDs, not money.
    id_context = any(k in lo for k in [
        "aid", "auth", "approval", "ref", "reference", "tran", "trans",
        "invoice #", "inv#", "order", "acct", "account", "card", "mastercard", "visa", "amex"
    ])

    if receipt_money_context and not id_context:
        # Find 3-6 digit integers not part of larger sequences.
        # Convert: 4749 -> 47.49, 474 -> 4.74
        int_pat = re.compile(r"\b(?P<int>\d{3,6})\b")
        for m in int_pat.finditer(t):
            raw = m.group(0)
            s = m.group("int") or ""

            # Skip years and dates-ish
            if len(s) == 4 and s.startswith(("19", "20")):
                continue

            # Skip obvious phone chunks (area codes etc.) by local neighborhood check
            neighborhood = t[max(0, m.start()-8):min(len(t), m.end()+8)]
            if re.search(r"\(\d{3}\)|\d{3}[-\s]\d{3}[-\s]\d{4}", neighborhood):
                continue

            # Convert implied cents
            try:
                iv = int(s)
            except Exception:
                continue

            # Guardrails: if it's too big to be cents money, ignore
            # (e.g. 9001391660 etc won't match due to 6 digit cap anyway)
            val = iv / 100.0
            if val <= 0 or val > 50000:
                continue

            # Extra guard: avoid integers that are clearly counts/codes by surrounding letters
            near = neighborhood.lower()
            if any(k in near for k in ["store", "register", "lane", "cashier", "receipt", "terminal"]):
                # those lines can still contain totals; don't block
                pass

            _add(val, raw, m.start())

    # --- De-dupe (value, raw, pos can vary; de-dupe by value+pos bucket) ---
    seen = set()
    dedup: List[Tuple[float, str, int]] = []
    for val, raw, pos in out:
        key = (round(val, 2), pos)
        if key in seen:
            continue
        seen.add(key)
        dedup.append((val, raw, pos))

    return dedup

def _window_has_decimal_money(window: str) -> bool:
    # If the window already contains explicit decimals like 47.49,
    # we should NOT trust implied-cents in the same window.
    return bool(re.search(r"\b\d{1,5}\.\d{2}\b", window or ""))



def _implied_cents_candidates_from_text(text: str) -> List[Tuple[float, str, int]]:
    """
    Implied cents integers like "4743" => 47.43.
    We MUST be strict because receipts contain many 4-6 digit IDs.

    Rules:
      - allow 3-7 digits but penalize / skip ID-ish contexts
      - skip if nearby there are obvious ID markers
      - skip if number is exactly 5 digits (common store/txn IDs) unless "$" is nearby (rare)
    """
    if not text:
        return []

    out: List[Tuple[float, str, int]] = []
    pat = re.compile(r"(?<!\d)(?P<num>\d{3,7})(?!\d)")

    for m in pat.finditer(text):
        raw = m.group(0)
        num = m.group("num") or ""
        if not num:
            continue

        # Local context window around the token
        ctx = (text[max(0, m.start() - 18): min(len(text), m.end() + 18)] or "").lower()

        # If it smells like an ID/reference/auth/etc, drop it.
        id_markers = [
            "id", "aid", "ref", "auth", "approval", "appr", "tran", "txn", "inv",
            "invoice", "order", "store", "register", "terminal", "cashier",
            "mastercard", "visa", "amex", "acct", "account",
        ]
        if any(k in ctx for k in id_markers):
            continue

        # 5-digit tokens are very often IDs (like your 34689). Skip by default.
        if len(num) == 5:
            # only allow if there's an explicit $ near it (rare but safer)
            if "$" not in ctx:
                continue

        try:
            iv = int(num)
        except Exception:
            continue

        val = round(iv / 100.0, 2)
        if val <= 0 or val > 50000:
            continue

        out.append((val, raw, m.start()))

    return out

def _extract_money_tokens(text: str) -> List[Tuple[float, str, int, str]]:
    """
    Combined token extractor:
      returns (value, raw, pos, kind)
    """
    out: List[Tuple[float, str, int, str]] = []
    for v, raw, pos in _money_candidates_from_text(text):
        out.append((v, raw, pos, "decimal"))
    for v, raw, pos in _implied_cents_candidates_from_text(text):
        out.append((v, raw, pos, "implied_cents"))
    return out


# -----------------------------------------------------------------------------
# Vendor extraction (improved for multipass OCR)
# -----------------------------------------------------------------------------

def _extract_vendor(lines: List[str], sections: Dict[str, List[str]]) -> Tuple[Optional[str], float, str, Optional[str]]:
    """
    Vendor heuristics:
      1) Alias match in vendor_pass/top region (strong)
      2) Alias match in full top region (strong)
      3) Labeled vendor lines ("From:", "Sold by", "Merchant") (medium)
      4) Merchant-like top line scoring (weak)
      5) If OCR gave garbage like mostly digits, mark low confidence + flag
    """
    if not lines:
        return None, 0.0, "No OCR lines.", None

    # Prefer vendor pass if present (your OCR top strip pass)
    vendor_block = sections.get("vendor_pass") or []
    soft_block = sections.get("softtext_pass") or []
    top_full = lines[:14]

    search_spaces: List[Tuple[str, str]] = []

    if vendor_block:
        search_spaces.append(("vendor_pass", "\n".join(vendor_block).lower()))
    if soft_block:
        search_spaces.append(("softtext_pass", "\n".join(soft_block).lower()))

    search_spaces.append(("top_full", "\n".join(top_full).lower()))
    search_spaces.append(("full", "\n".join(lines).lower()))

    def _norm(s: str) -> str:
        # normalize to alnum only (handles "auto zone", "auto-zone", "auto. zone", etc)
        return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

    def _alias_hit(alias: str, hay: str) -> bool:
        """
        More forgiving alias match for OCR noise:
        - exact substring (fast path)
        - normalized substring (handles spaces/punct)
        - token prefix match (handles truncation like 'autoz' / 'autozz')
        """
        a = (alias or "").lower().strip()
        h = (hay or "").lower()
        if not a or not h:
            return False

        # 1) exact substring
        if a in h:
            return True

        # 2) normalized substring
        aN = _norm(a)
        hN = _norm(h)
        if aN and aN in hN:
            return True

        # 3) token prefix match (guarded)
        # Example: "autozz" should hit "autozone"
        tokens = re.findall(r"[a-z0-9']{3,}", h)
        a4 = aN[:4] if len(aN) >= 4 else aN
        for t in tokens:
            tN = _norm(t)
            if not tN:
                continue
            if a4 and tN.startswith(a4):
                # also require some length closeness so "auto" doesn't match everything
                if abs(len(tN) - len(aN)) <= 4:
                    return True

        return False

    # 1/2) Alias match across prioritized blocks
    best_vendor = None
    best_score = 0.0
    best_alias = None
    best_src = None

    for space_name, hay in search_spaces:
        if not hay:
            continue
        for canon, aliases in VENDOR_ALIASES.items():
            for a in aliases:
                a_lo = a.lower()
                if not a_lo:
                    continue
                if _alias_hit(a_lo, hay):
                    score = 0.84
                    # vendor_pass gets a bump
                    if space_name == "vendor_pass":
                        score += 0.10
                    elif space_name == "softtext_pass":
                        score += 0.06
                    elif space_name == "top_full":
                        score += 0.04

                    # bump if exact canonical is present too
                    if canon.lower() in hay:
                        score += 0.03

                    score = _clamp01(score)
                    if score > best_score:
                        best_score = score
                        best_vendor = canon
                        best_alias = a
                        best_src = f"alias_match:{space_name}"

        # If we got a near-perfect match from vendor_pass, stop early
        if best_vendor and best_score >= 0.92 and space_name in ("vendor_pass", "softtext_pass"):
            break

    if best_vendor:
        return (
            best_vendor,
            _to_conf_100(best_score),
            f"Matched vendor alias '{best_alias}' in {best_src}.",
            best_src,
        )

    # 3) Labeled vendor lines near top
    labeled_patterns = [
        r"\b(from|sold by|merchant|seller)\s*[:\-]\s*(.+)$",
        r"\b(merchant)\b\s+(.+)$",
    ]
    top = lines[:20]
    for ln in top:
        for pat in labeled_patterns:
            m = re.search(pat, ln, flags=re.I)
            if m:
                cand = m.group(2).strip()
                cand = _collapse_spaces(_strip_noise(cand))
                if 2 <= len(cand) <= 50:
                    return (
                        cand,
                        _to_conf_100(0.68),
                        f"Found vendor in labeled line: '{ln}'.",
                        "labeled_vendor",
                    )

    # 4) Merchant-like top line scoring
    # Avoid addresses/phones/urls/totals/dates
    best_line = None
    best_line_score = 0.0
    for ln in top_full:
        lo = ln.lower()

        if _line_has_any(lo, TOTAL_LABELS + TAX_LABELS + DATE_LABELS + SUBTOTAL_LABELS):
            continue
        if any(k in lo for k in ["street", " st ", " st.", "road", " rd", " rd.", "ave", "suite", "phone", "tel", "www", ".com", "@"]):
            continue

        # Score alpha-heaviness and "merchant-ness"
        alpha = sum(ch.isalpha() for ch in ln)
        digit = sum(ch.isdigit() for ch in ln)
        length = len(ln)

        if length < 3 or length > 55:
            continue

        score = 0.0
        # must have some letters
        if alpha >= 4:
            score += 0.30
        # penalize digit-heavy lines
        if digit > alpha:
            score -= 0.20
        # uppercase-ish bump
        upp = sum(ch.isupper() for ch in ln if ch.isalpha())
        if alpha > 0 and (upp / alpha) >= 0.60:
            score += 0.12

        # bump if it looks like a brand name (few words, not too long)
        words = ln.split()
        if 1 <= len(words) <= 4:
            score += 0.10

        score = _clamp01(score)
        if score > best_line_score:
            best_line_score = score
            best_line = ln

    if best_line:
        clean = _collapse_spaces(_strip_noise(best_line))
        conf = _to_conf_100(0.30 + best_line_score * 0.30)  # cap weak heuristic
        return (
            clean,
            conf,
            f"Fallback vendor guess from early merchant-like line: '{best_line}'.",
            "heuristic_top_line",
        )

    return None, 0.0, "No reliable vendor signal found.", None


# -----------------------------------------------------------------------------
# Date extraction (robust)
# -----------------------------------------------------------------------------

_DATE_PATTERNS = [
    # 01/27/2026 or 1/7/26
    (re.compile(r"\b(?P<m>\d{1,2})[\/\-](?P<d>\d{1,2})[\/\-](?P<y>\d{2,4})\b"), "mdy_slash"),
    # 2026-01-27
    (re.compile(r"\b(?P<y>\d{4})[\/\-](?P<m>\d{1,2})[\/\-](?P<d>\d{1,2})\b"), "ymd_dash"),
    # Jan 27 2026 / January 27, 2026
    (re.compile(
        r"\b(?P<mon>jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\.?\s+(?P<d>\d{1,2})(?:,)?\s+(?P<y>\d{2,4})\b",
        re.I
    ), "mon_d_y"),
    # 27 Jan 2026
    (re.compile(
        r"\b(?P<d>\d{1,2})\s+(?P<mon>jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\.?\s+(?P<y>\d{2,4})\b",
        re.I
    ), "d_mon_y"),
]

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def _extract_date(lines: List[str], joined: str, sections: Dict[str, List[str]]) -> Tuple[Optional[str], float, str]:
    if not joined.strip():
        return None, 0.0, "No OCR text."

    candidates: List[Tuple[str, float, str]] = []  # (iso, score01, reason)

    # Prioritize numeric pass if present (your OCR runs a digits pass)
    scan_blocks: List[Tuple[str, str]] = []
    if sections.get("numeric_pass"):
        scan_blocks.append(("numeric_pass", "\n".join(sections["numeric_pass"])))
    scan_blocks.append(("top_full", "\n".join(lines[:35])))
    scan_blocks.append(("full", joined))

    # 1) Label proximity scan (strong) in top_full
    for i, ln in enumerate(lines[:40]):
        lo = ln.lower()
        if any(lbl in lo for lbl in DATE_LABELS):
            window = _best_line_window(lines, i, radius=3)
            for iso, base_reason in _date_candidates_from_text(window):
                candidates.append((iso, 0.86, f"{base_reason} Found near date label in: '{ln}'."))

    # 2) Generic scan in prioritized blocks
    for name, block in scan_blocks:
        for iso, base_reason in _date_candidates_from_text(block):
            base = 0.62 if name == "full" else 0.70
            if name == "numeric_pass":
                base += 0.04
            candidates.append((iso, base, f"{base_reason} Found by scan in {name}."))

    if not candidates:
        return None, 0.0, "No date pattern detected."

    # Pick best by adjusted plausibility
    today = datetime.utcnow().date()
    best_iso = None
    best_score = -1.0
    best_reason = ""

    for iso, score, reason in candidates:
        dt = _parse_iso_date(iso)
        if not dt:
            continue

        # penalize far future
        if dt > today.replace(year=today.year + 2):
            score -= 0.35
            reason += " Penalized: implausible far-future date."

        # penalize very old dates
        if dt < today.replace(year=today.year - 15):
            score -= 0.15
            reason += " Penalized: very old date."

        # slight bump for dates in the last ~2 years (common receipt window)
        if today.replace(year=today.year - 2) <= dt <= today:
            score += 0.04

        score = _clamp01(score)
        if score > best_score:
            best_score = score
            best_iso = iso
            best_reason = reason

    if not best_iso:
        return None, 0.0, "Date candidates existed but none were valid."

    return best_iso, _to_conf_100(best_score), best_reason


def _date_candidates_from_text(text: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for pat, tag in _DATE_PATTERNS:
        for m in pat.finditer(text or ""):
            iso = _normalize_date_match(m, tag)
            if iso:
                out.append((iso, f"Matched date pattern '{tag}'."))
    # de-dup preserving order
    seen = set()
    dedup: List[Tuple[str, str]] = []
    for iso, r in out:
        if iso not in seen:
            seen.add(iso)
            dedup.append((iso, r))
    return dedup


def _normalize_date_match(m: re.Match, tag: str) -> Optional[str]:
    try:
        if tag in ("mdy_slash", "ymd_dash"):
            y = int(m.group("y"))
            mo = int(m.group("m"))
            d = int(m.group("d"))
            if y < 100:
                y = 2000 + y if y <= 68 else 1900 + y
        elif tag in ("mon_d_y", "d_mon_y"):
            y = int(m.group("y"))
            if y < 100:
                y = 2000 + y if y <= 68 else 1900 + y
            mon_raw = (m.group("mon") or "").lower().strip(".")
            mo = _MONTHS.get(mon_raw[:3], None) if mon_raw else None
            d = int(m.group("d"))
            if mo is None:
                return None
        else:
            return None

        dt = datetime(y, mo, d).date()
        return dt.isoformat()
    except Exception:
        return None


def _parse_iso_date(iso: str) -> Optional[date]:
    try:
        return datetime.strptime(iso, "%Y-%m-%d").date()
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Tax extraction (label-driven + totals-pass aware)
# -----------------------------------------------------------------------------

def _extract_money_values_from_text(text: str, labeled_window: bool = False) -> List[float]:
    """
    Safe helper: returns money-like float values from a blob of text.
    Uses existing money token extractor if available; otherwise regex fallback.
    """
    vals: List[float] = []

    # If you already have _extract_money_tokens(text) in this file, use it.
    if "_extract_money_tokens" in globals():
        try:
            tokens = _extract_money_tokens(text)  # expected: (val, raw, pos, kind)
            for val, raw, pos, kind in tokens:
                # implied cents is only trusted when we're in labeled context
                if kind == "implied_cents" and not labeled_window:
                    continue
                vals.append(float(val))
            return vals
        except Exception:
            pass

    # Regex fallback
    for m in re.finditer(r"(?<!\w)(\d{1,6})(?:\.(\d{1,2}))?(?!\w)", text):
        whole = m.group(1)
        dec = m.group(2)
        if dec is None:
            continue
        try:
            vals.append(float(f"{whole}.{dec}"))
        except Exception:
            continue

    return vals

def _is_bad_total_context(text: str) -> bool:
    """
    Returns True when a line/window is likely NOT a grand total candidate.
    Useful to avoid grabbing:
      - item totals
      - subtotals
      - tax lines
      - discounts, change, tender, etc.
    Works for both paper receipts and online invoices.
    """
    if not text:
        return False

    t = text.lower()

    # Anything that is explicitly NOT the final total
    bad_hints = (
        "item total", "items total", "item(s) total",
        "subtotal", "sub total", "total before tax", "pretax", "pre tax", "before tax",
        "tax", "sales tax", "vat", "gst", "hst",
        "discount", "coupon", "savings",
        "change", "cash", "tender", "payment", "paid", "balance", "amount due",
        "tip", "gratuity",
        "shipping", "handling",
        "deposit",
        "auth", "authorization",
    )

    # If it contains a strong final-total label, it's not "bad"
    # (these should win even if the line also contains other words)
    good_total_hints = (
        "grand total",
        "order total",
        "total due",
        "amount due",
        "balance due",
        "total:",
    )

    if any(g in t for g in good_total_hints):
        return False

    return any(b in t for b in bad_hints)

def _extract_tax(
    lines: List[str],
    joined: str,
    sections: Dict[str, List[str]],
) -> Tuple[Optional[float], float, str]:
    """
    Tax extraction (receipt-first, robust):

    Priority:
    1) Explicit tax lines (sales tax / estimated tax / tax to be collected / vat / gst / pst / hst)
       - prefer totals_pass lines, then full
       - ignore "before tax" / "taxable" / "tax rate" traps
    2) Infer from subtotal-ish and total if both found:
       tax = total - subtotal  (only if plausible)
    """

    if not (joined or "").strip():
        return None, 0.0, "No OCR text."

    import re

    def norm(s: str) -> str:
        return (s or "").lower().strip()

    # --- Labels that usually mean "this number is tax" ---
    TAX_STRONG = (
        "sales tax",
        "estimated tax",
        "tax to be collected",
        "tax collected",
        "tax amount",
        "vat",
        "gst",
        "pst",
        "hst",
        "qst",
        "iva",
        "mwst",
        "tva",
    )

    # "tax:" alone is common, but dangerous. We'll treat it as medium strength.
    TAX_MEDIUM = (
        "tax:",
        " tax ",
        "tax ",
    )

    # --- Phrases that contain "tax" but are NOT tax amounts ---
    TAX_TRAPS = (
        "before tax",
        "total before tax",
        "pre-tax",
        "pretax",
        "taxable",
        "tax rate",
        "tax %",
        "tax percent",
        "% tax",
        "tax id",
        "tax no",
        "tax number",
        "tax invoice",  # often header, not amount
    )

    # Subtotal-ish labels (for inference)
    SUBTOTAL_LABELS = (
        "subtotal",
        "sub total",
        "total before tax",
        "before tax total",
        "pre-tax total",
        "pretax total",
        "merchandise",
        "items subtotal",
    )

    # Total labels that mean grand total (to infer tax)
    TOTAL_LABELS_LOCAL = (
        "grand total",
        "order total",
        "amount due",
        "balance due",
        "total:",
        "total $",
        "total ",
    )

    # helper: extract last money value from a line
    def last_money(line: str) -> Optional[float]:
        vals = _extract_money_values_from_text(line, labeled_window=True)
        if not vals:
            return None
        return float(vals[-1])

    # helper: check label-ish presence
    def has_any(hay: str, needles: Tuple[str, ...]) -> bool:
        h = norm(hay)
        return any(n in h for n in needles)

    # Build scan lines preferring totals_pass first
    scan_lines: List[Tuple[str, str]] = []
    if sections and sections.get("totals_pass"):
        for ln in sections["totals_pass"]:
            scan_lines.append(("totals_pass", ln))
    for ln in lines:
        scan_lines.append(("full", ln))

    # Track best explicit tax candidate
    best_val: Optional[float] = None
    best_score: float = 0.0
    best_reason: str = "No tax signal found."

    # Track subtotal and total for inference
    seen_subtotal: Optional[float] = None
    seen_total: Optional[float] = None
    seen_subtotal_src: Optional[str] = None
    seen_total_src: Optional[str] = None

    # Pass A: capture subtotal + total candidates (for inference), and explicit tax lines
    for src, ln in scan_lines:
        t = norm(ln)
        if not t:
            continue

        # Capture subtotal-ish for inference (ignore if looks like a tax line itself)
        if seen_subtotal is None and has_any(t, SUBTOTAL_LABELS):
            v = last_money(ln)
            if v is not None:
                seen_subtotal = v
                seen_subtotal_src = f"{src}: '{ln}'"

        # Capture total-ish for inference
        # NOTE: total extractor is your source of truth; this is just a fallback inference input.
        if seen_total is None and has_any(t, TOTAL_LABELS_LOCAL):
            # Avoid picking up "item total" etc by refusing bad contexts
            # (Reuse your bad-total context if it exists)
            try:
                if "_is_bad_total_context" in globals() and _is_bad_total_context(t):
                    pass
                else:
                    v = last_money(ln)
                    if v is not None:
                        seen_total = v
                        seen_total_src = f"{src}: '{ln}'"
            except Exception:
                v = last_money(ln)
                if v is not None:
                    seen_total = v
                    seen_total_src = f"{src}: '{ln}'"

        # Skip trap lines for explicit tax detection
        if any(trap in t for trap in TAX_TRAPS):
            continue

        # Explicit tax detection
        is_strong = any(lbl in t for lbl in TAX_STRONG)
        is_medium = (not is_strong) and any(lbl in t for lbl in TAX_MEDIUM)

        if not (is_strong or is_medium):
            continue

        v = last_money(ln)
        if v is None:
            continue

        # Score explicit tax candidates
        score = 0.70 if is_medium else 0.85

        if src == "totals_pass":
            score += 0.08

        # Dollar sign bump
        if "$" in ln:
            score += 0.03

        # Implausibility penalties
        if v < 0.01:
            score -= 0.50
        # tax is rarely > $500 on typical small receipts; keep but penalize
        if v > 500:
            score -= 0.25

        # If we already know a total, tax should not exceed total
        if seen_total is not None and v > seen_total:
            score -= 0.60

        score = _clamp01(score)

        if score > best_score:
            best_score = score
            best_val = v
            strength = "strong" if is_strong else "medium"
            best_reason = f"Matched {strength} tax label; Source: ({src}) '{ln}'"

    # If we found an explicit tax, return it
    if best_val is not None:
        return round(float(best_val), 2), _to_conf_100(best_score), best_reason

    # Pass B: infer tax from subtotal + total
    if seen_total is not None and seen_subtotal is not None:
        inferred = round(float(seen_total) - float(seen_subtotal), 2)

        # Plausibility: tax should be >= 0 and not ridiculous
        # Allow 0.00 (some receipts)
        if inferred >= 0.0:
            # If inferred tax is huge fraction, treat as suspicious and refuse
            if seen_total > 0 and (inferred / seen_total) <= 0.25:
                conf = 0.70
                # Prefer inference slightly more if both came from totals_pass
                if (seen_total_src and "totals_pass" in seen_total_src) and (seen_subtotal_src and "totals_pass" in seen_subtotal_src):
                    conf += 0.05
                conf = _clamp01(conf)
                return inferred, _to_conf_100(conf), (
                    f"Inferred tax = total - subtotal ({seen_total:.2f} - {seen_subtotal:.2f}). "
                    f"Total from {seen_total_src}; subtotal from {seen_subtotal_src}"
                )

    return None, 0.0, "No tax line detected."


# -----------------------------------------------------------------------------
# Total extraction (label + totals-pass + implied cents + sanity)
# -----------------------------------------------------------------------------

@dataclass
class _TotalCandidate:
    value: float
    score: float
    reason: str
    source_line: str
    has_total_label: bool

TOTAL_LABEL_PATTERNS = (
    r"grand\s*total",
    r"\btotal\b\s*:",
    r"\btotal\b\s+\$",
    r"amount\s+due",
    r"balance\s+due",
    r"\btotal\b",
    r"order\s*total",
)

def _has_total_label(text: str) -> bool:
    t= (text or "").lower()
    return any(re.search(p, t, flags=re.IGNORECASE) for p in TOTAL_LABEL_PATTERNS)

def _extract_total(
    lines: List[str],
    joined: str,
    sections: Dict[str, List[str]],
    tax_value: Optional[float],
) -> Tuple[Optional[float], float, str]:
    """
    Receipt-first grand total extraction.

    Strategy:
    1) Scan *entire* text for strong total labels (Grand Total, Amount Due, Balance Due, Total Due, etc.).
       If found, extract the best nearby money value (same line or within a small window).
    2) If no strong label hit, use weaker "total" label windows (still avoiding subtotal/item total/tax/tender).
    3) If still nothing, fall back to global candidates scored by plausibility + context penalties.

    Returns: (total_value, confidence_0_to_100, reasoning_str)
    """

    if not (joined or "").strip() and not lines:
        return None, 0.0, "No OCR text."

    # ---------- helpers ----------
    MONEY_RE = re.compile(
        r"(?<!\w)"
        r"(?:\$?\s*)"
        r"(\d{1,6}(?:[,\s]\d{3})*(?:\.\d{1,2})?|\d{1,6})"
        r"(?!\w)"
    )

    def _norm_text(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip())

    def _parse_money(token: str, labeled_window: bool) -> Optional[float]:
        """
        Parses money from OCR token:
        - supports: 20.09, $20.09, 1,234.56
        - supports truncated: 47.4 -> 47.40
        - supports implied cents ints like 4749 -> 47.49 ONLY when labeled_window=True
        """
        if not token:
            return None
        t = token.strip()
        t = t.replace(",", "").replace(" ", "")

        # Remove leading $ if present
        if t.startswith("$"):
            t = t[1:]

        # Must be numeric-ish
        if not re.fullmatch(r"\d+(\.\d{1,2})?", t):
            return None

        # Implied cents (4749 => 47.49) ONLY in labeled windows
        if labeled_window and re.fullmatch(r"\d{3,6}", t) and "." not in t:
            # 3+ digits could be cents-implied; 2 digits => cents, rest => dollars
            # e.g., 2009 -> 20.09, 4749 -> 47.49
            if len(t) >= 3:
                dollars = t[:-2]
                cents = t[-2:]
                try:
                    return float(f"{int(dollars)}.{int(cents):02d}")
                except Exception:
                    return None

        # Normal decimal / integer
        try:
            val = float(t)
        except Exception:
            return None

        # Truncated decimals: 47.4 -> 47.40
        if re.fullmatch(r"\d+\.\d", t):
            val = float(f"{val:.2f}")

        return val

    # Context filters (keep these tight to avoid grabbing item lines)
    STRONG_LABEL_PATTERNS = (
        r"grand\s*total",
        r"total\s+due",
        r"amount\s+due",
        r"balance\s+due",
        r"amount\s+payable",
        r"pay\s+this\s+amount",
        r"order\s*total",
    )
    WEAK_LABEL_PATTERNS = (
        r"\btotal\b\s*:?",
        r"\btotal\b\s+\$",
        r"\btotal\b",
    )

    BAD_CONTEXT_KEYWORDS = (
        "subtotal", "sub total",
        "item total", "items total",
        "line total", "extended", "ext price", "extension",
        "merchandise", "merch total",
        "taxable", "vat",
        "tip", "gratuity",
        "tender", "cash", "change",
        "amount tendered",
        "payment", "debit", "credit",
        "card", "visa", "mastercard",
        "auth", "approval",
        "discount", "savings",
        "refund",
    )

    ITEM_MATH_RE = re.compile(r"\b\d+\s*(?:x|@)\s*\$?\s*\d+(\.\d{1,2})?\b", re.IGNORECASE)

    def _has_any_pattern(s: str, patterns: Tuple[str, ...]) -> bool:
        lo = (s or "").lower()
        return any(re.search(p, lo, flags=re.IGNORECASE) for p in patterns)

    def _is_bad_context(s: str) -> bool:
        lo = (s or "").lower()
        # If strong label is present, don't treat it as bad even if other keywords appear
        if _has_any_pattern(lo, STRONG_LABEL_PATTERNS):
            return False
        if any(k in lo for k in BAD_CONTEXT_KEYWORDS):
            return True
        if ITEM_MATH_RE.search(lo):
            return True
        return False

    def _extract_money_values_from_text(s: str, labeled_window: bool) -> List[float]:
        vals: List[float] = []
        for m in MONEY_RE.finditer(s or ""):
            token = m.group(1)
            v = _parse_money(token, labeled_window=labeled_window)
            if v is None:
                continue
            # Ignore absurdly small item-like values unless labeled
            vals.append(v)
        return vals

    def _score(val: float, ctx: str, has_label: bool) -> Tuple[float, List[str]]:
        """
        Score in [0,1]. Higher is better.
        """
        why: List[str] = []
        score = 0.90 if has_label else 0.55
        why.append("Labeled total window" if has_label else "Unlabeled candidate")

        lo = (ctx or "").lower()

        # Penalize obvious non-total contexts
        if _is_bad_context(ctx):
            score -= 0.35
            why.append("Penalized: bad context")

        # Penalize tax lines hard
        if "tax" in lo or "vat" in lo:
            score -= 0.30
            why.append("Penalized: tax context")

        # Plausibility
        if val < 1.00:
            score -= 0.25
            why.append("Penalized: too small")
        elif val > 20000:
            score -= 0.20
            why.append("Penalized: unusually large")

        # If we have a tax_value and candidate equals tax_value (or close), penalize
        if tax_value is not None and abs(val - float(tax_value)) <= 0.02:
            score -= 0.35
            why.append("Penalized: matches tax value")

        # Favor two-decimal values
        if abs(val * 100 - round(val * 100)) < 1e-6:
            score += 0.03
            why.append("Bump: currency-like precision")

        # Clamp
        score = max(0.0, min(1.0, score))
        return score, why

    # Build a unified line list
    all_lines: List[str] = []
    if lines:
        all_lines.extend([_norm_text(x) for x in lines if (x or "").strip()])
    else:
        all_lines.extend([_norm_text(x) for x in (joined or "").splitlines() if (x or "").strip()])

    # Add any section lines if provided
    for sec_name, sec_lines in (sections or {}).items():
        for x in sec_lines or []:
            tx = _norm_text(x)
            if tx:
                all_lines.append(tx)

    # De-dupe while preserving order
    seen = set()
    deduped: List[str] = []
    for l in all_lines:
        if l not in seen:
            seen.add(l)
            deduped.append(l)
    all_lines = deduped

    # ---------- pass 1: strong label windows ----------
    candidates: List[Tuple[float, float, str]] = []  # (score, val, reason)
    strong_hits = 0

    for i, line in enumerate(all_lines):
        if _has_any_pattern(line, STRONG_LABEL_PATTERNS):
            strong_hits += 1
                        # Prefer value on the SAME line as the strong label (Amazon: "Order Total: $35.62")
            line_vals = _extract_money_values_from_text(line, labeled_window=True)
            if line_vals:
                v = line_vals[-1]
                sc, why = _score(v, line, has_label=True)
                sc = min(1.0, sc + 0.10)  # bigger bump: label + value same line
                why.append("Strong label match (same line)")
                candidates.append((sc, v, f"{' ; '.join(why)}. Source: '{line}'"))
                continue
            # Window: current line + next 2 lines (totals sometimes wrap)
            window_lines = all_lines[i : min(len(all_lines), i + 3)]
            window_text = " | ".join(window_lines)

            # Avoid excluding strong labels, but still avoid grabbing wrong value in same line if multiple
            vals = _extract_money_values_from_text(window_text, labeled_window=True)
            if not vals:
                continue

            # If multiple values, prefer the last one in the window (often the total sits after label)
            # but also score each.
            for v in vals:
                sc, why = _score(v, window_text, has_label=True)
                # Small bump for being in a strong label window
                sc = min(1.0, sc + 0.05)
                why.append("Strong label match")
                candidates.append((sc, v, f"{' ; '.join(why)}. Source: '{window_text}'"))

    # If we found any strong-label candidates, take best and return immediately
    if candidates and strong_hits > 0:
        best = max(candidates, key=lambda t: t[0])
        conf = round(best[0] * 100.0, 2)
        return float(best[1]), conf, best[2]

    # ---------- pass 2: weak label windows ----------
    candidates = []
    weak_hits = 0

    for i, line in enumerate(all_lines):
        if _has_any_pattern(line, WEAK_LABEL_PATTERNS) and not _is_bad_context(line):
            weak_hits += 1
            window_lines = all_lines[i : min(len(all_lines), i + 3)]
            window_text = " | ".join(window_lines)

            vals = _extract_money_values_from_text(window_text, labeled_window=True)
            if not vals:
                continue
            for v in vals:
                sc, why = _score(v, window_text, has_label=True)
                # Smaller bump than strong-label
                sc = min(1.0, sc + 0.03)
                why.append("Weak label match")
                candidates.append((sc, v, f"{' ; '.join(why)}. Source: '{window_text}'"))

    if candidates and weak_hits > 0:
        best = max(candidates, key=lambda t: t[0])
        conf = round(best[0] * 100.0, 2)
        return float(best[1]), conf, best[2]

    # ---------- pass 3: global fallback ----------
    # Use entire receipt but penalize bad contexts
    candidates = []
    for i, line in enumerate(all_lines):
        if _is_bad_context(line):
            continue
        vals = _extract_money_values_from_text(line, labeled_window=False)
        for v in vals:
            sc, why = _score(v, line, has_label=False)
            candidates.append((sc, v, f"{' ; '.join(why)}. Source: '{line}'"))

    # If nothing left after filtering, loosen filter slightly (still avoid item math)
    if not candidates:
        for i, line in enumerate(all_lines):
            if ITEM_MATH_RE.search((line or "").lower()):
                continue
            vals = _extract_money_values_from_text(line, labeled_window=False)
            for v in vals:
                sc, why = _score(v, line, has_label=False)
                # Slight penalty since we had to loosen
                sc = max(0.0, sc - 0.05)
                why.append("Loosened context filter")
                candidates.append((sc, v, f"{' ; '.join(why)}. Source: '{line}'"))

    if not candidates:
        return None, 0.0, "No money candidates found."

    best = max(candidates, key=lambda t: t[0])
    conf = round(best[0] * 100.0, 2)
    return float(best[1]), conf, best[2]