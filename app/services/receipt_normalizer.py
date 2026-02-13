# app/services/receipt_normalizer.py
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Union

from app.schemas import ReceiptParsed


# -----------------------------------------------------------------------------
# Small cleaners (keep v1 predictable)
# -----------------------------------------------------------------------------

def _clean_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        return v if v else None
    # allow numeric vendor-like values to become strings only if they’re not empty
    v = str(value).strip()
    return v if v else None


def _clean_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # strip currency/letters; keep digits, comma, dot, minus
        s = re.sub(r"[^0-9\.,\-]", "", s)

        # handle "1,234.56" -> "1234.56"
        if "," in s and "." in s:
            s = s.replace(",", "")
        # handle "12,34" -> "12.34"
        elif s.count(",") == 1 and "." not in s:
            s = s.replace(",", ".")

        try:
            return float(s)
        except Exception:
            return None

    return None


def _to_dict(parsed: Union[ReceiptParsed, Dict[str, Any], None]) -> Dict[str, Any]:
    if parsed is None:
        return {}
    if hasattr(parsed, "model_dump"):
        return parsed.model_dump()
    if isinstance(parsed, dict):
        return parsed
    return {}


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def normalize_receipt(parsed: Union[ReceiptParsed, Dict[str, Any], None]) -> Dict[str, Any]:
    """
    Normalizes ReceiptParsed (or dict) into a stable dict shape that matches ReceiptNormalized.
    This function MUST return a dict (main.py wraps it into ReceiptNormalized).
    """
    p = _to_dict(parsed)

    vendor = _clean_str(p.get("vendor"))
    date = _clean_str(p.get("date"))
    total = _clean_float(p.get("total"))
    tax = _clean_float(p.get("tax"))
    category = _clean_str(p.get("category"))

    existing_flags = p.get("flags") or []
    if not isinstance(existing_flags, list):
        existing_flags = []

    needs_review = bool(p.get("needs_review") or False) or (len(existing_flags) > 0)

    result: Dict[str, Any] = {
        # vendor block
        "vendor": vendor,
        "vendor_confidence": float(p.get("vendor_confidence") or 0.0),
        "vendor_reasoning": p.get("vendor_reasoning") or "",
        "vendor_source": p.get("vendor_source"),

        # date block
        "date": date,
        "date_confidence": float(p.get("date_confidence") or 0.0),
        "date_reasoning": p.get("date_reasoning") or "",

        # total block
        "total": total,
        "total_confidence": float(p.get("total_confidence") or 0.0),
        "total_reasoning": p.get("total_reasoning") or "",

        # tax
        "tax": tax,

        # category block
        "category": category,
        "category_confidence": float(p.get("category_confidence") or 0.0),
        "category_reasoning": p.get("category_reasoning") or "",

        # review
        "flags": existing_flags,
        "needs_review": needs_review,
    }

    return result