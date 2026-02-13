from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from app.categories.mappings import (
    VENDOR_CATEGORY_MAP,
    KEYWORD_CATEGORY_MAP,
    BUSINESS_TYPE_DEFAULTS,
)


# ------------------------------------------------------------------------------
# Deterministic Rule Layer (v1)
# ------------------------------------------------------------------------------
# Purpose:
# - Run BEFORE the heuristic engine (engine.py) if you wire it that way
# - Capture "obvious" cases with high confidence
# - Provide a single place to add accountant-approved rules
#
# Output format matches engine.py:
#   {"category": str|None, "confidence": float, "reasoning": str}
# ------------------------------------------------------------------------------


def _norm(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def rule_match_vendor(vendor: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Strongest rule: canonical vendor -> category map
    Uses substring matching with preference for longer matches to avoid false positives.

    Examples:
        "Shell #1234" -> matches "Shell" -> "Fuel"
        "AUTOZONE STORE 5432" -> matches "AutoZone" -> "Car & Truck"
        "Target Specialty Products" -> matches "Target Specialty Products" (not "Target")
    """
    if not vendor:
        return None

    vendor_norm = _norm(vendor)

    # Collect all matches and sort by length (longest first for specificity)
    matches = []
    for vendor_key, category in VENDOR_CATEGORY_MAP.items():
        vendor_key_norm = _norm(vendor_key)
        if vendor_key_norm in vendor_norm:
            matches.append((vendor_key, category, len(vendor_key)))

    if not matches:
        return None

    # Return the longest match (most specific)
    matches.sort(key=lambda x: x[2], reverse=True)
    best_vendor, best_category, _ = matches[0]

    return {
        "category": best_category,
        "confidence": 0.95,
        "reasoning": f"Vendor mapping matched: '{best_vendor}' in '{vendor}'",
    }


def rule_match_keywords(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Match any keyword in the provided text (explanation or OCR).
    Uses simple substring search.
    """
    t = _norm(text)
    if not t:
        return None

    for kw, cat in KEYWORD_CATEGORY_MAP.items():
        if kw in t:
            return {
                "category": cat,
                "confidence": 0.80,
                "reasoning": f"Keyword mapping matched: '{kw}'",
            }
    return None


def rule_match_business_default(business_type: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    If business type is known, provide a default category when nothing else hits.
    """
    bt = _norm(business_type)
    if not bt:
        return None
    if bt in BUSINESS_TYPE_DEFAULTS:
        return {
            "category": BUSINESS_TYPE_DEFAULTS[bt],
            "confidence": 0.55,
            "reasoning": f"Business type default used: {business_type}",
        }
    return None


def apply_category_rules(
    vendor: Optional[str] = None,
    explanation: Optional[str] = None,
    ocr_text: Optional[str] = None,
    business_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run deterministic rules in priority order:
        1) vendor mapping
        2) explanation keywords
        3) OCR keywords
        4) business type default

    Returns:
        {"category": str|None, "confidence": float, "reasoning": str}
    """

    # 1) vendor
    hit = rule_match_vendor(vendor)
    if hit:
        return hit

    # 2) explanation keywords
    hit = rule_match_keywords(explanation)
    if hit:
        hit["reasoning"] = f"Explanation rule: {hit['reasoning']}"
        return hit

    # 3) OCR text keywords
    hit = rule_match_keywords(ocr_text)
    if hit:
        hit["reasoning"] = f"OCR rule: {hit['reasoning']}"
        return hit

    # 4) business default
    hit = rule_match_business_default(business_type)
    if hit:
        return hit

    return {"category": None, "confidence": 0.0, "reasoning": "No deterministic rule matched"}