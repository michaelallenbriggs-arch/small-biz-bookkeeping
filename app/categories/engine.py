# app/categories/engine.py
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from app.categories.mappings import (
    KEYWORD_CATEGORY_MAP,
    BUSINESS_TYPE_HINTS,
)


# ------------------------------------------------------------------------------
# v1 Category Engine
# ------------------------------------------------------------------------------
# Goal:
# - Provide a reasonable bookkeeping category suggestion
# - Use hierarchy: explanation > OCR text > vendor
# - Return {category, confidence, reasoning}
#
# This is intentionally simple and deterministic for v1.
# You can later swap this for an LLM or embeddings-based classifier without
# changing your main.py, as long as you keep the same return shape.
# ------------------------------------------------------------------------------


# A small, practical v1 taxonomy (expand as needed)
CATEGORIES = [
    "Advertising & Marketing",
    "Bank Fees",
    "Car & Truck",
    "Contract Labor",
    "Equipment",
    "Insurance",
    "Meals",
    "Office Supplies",
    "Other",
    "Rent",
    "Repairs & Maintenance",
    "Software & Subscriptions",
    "Supplies",
    "Travel",
    "Utilities",
    "Fuel",
]

# Keyword buckets (lowercase substring matching)
KEYWORDS = {
    "Fuel": [
        "fuel", "gas", "gasoline", "diesel", "pump", "shell", "exxon", "chevron", "bp", "sunoco"
    ],
    "Car & Truck": [
        "autozone", "auto zone", "advance auto", "o'reilly", "oreilly", "tires", "tire", "oil change",
        "brake", "battery", "wiper", "alignment"
    ],
    "Office Supplies": [
        "office", "staples", "paper", "printer", "ink", "toner", "notebook", "pens", "post-it"
    ],
    "Software & Subscriptions": [
        "subscription", "saas", "software", "monthly", "annual", "stripe", "quickbooks", "adobe",
        "microsoft 365", "google workspace", "aws", "azure", "gcp", "dropbox", "notion"
    ],
    "Supplies": [
        "supplies", "supply", "inventory", "restock", "materials"
    ],
    "Repairs & Maintenance": [
        "repair", "maintenance", "service", "labor", "parts", "fix", "replace"
    ],
    "Equipment": [
        "equipment", "tool", "tools", "machine", "hardware", "laptop", "computer", "monitor", "router"
    ],
    "Advertising & Marketing": [
        "marketing", "advertising", "ads", "facebook ads", "google ads", "promotion", "sponsor"
    ],
    "Meals": [
        "restaurant", "meal", "lunch", "dinner", "breakfast", "cafe", "coffee", "starbucks",
        "mcdonald", "subway", "doordash", "uber eats"
    ],
    "Travel": [
        "hotel", "airbnb", "flight", "airline", "uber", "lyft", "taxi", "rental car",
        "parking", "toll"
    ],
    "Utilities": [
        "electric", "water", "internet", "wifi", "utility", "phone bill", "verizon", "at&t", "t-mobile"
    ],
    "Insurance": [
        "insurance", "premium", "policy"
    ],
    "Rent": [
        "rent", "lease"
    ],
    "Bank Fees": [
        "fee", "service charge", "overdraft", "wire fee", "atm fee"
    ],
}

# Business-type biasing (optional)
# examples: expand as you actually onboard niches
BUSINESS_TYPE_HINTS = {
    "realtor": {
        "Advertising & Marketing": ["listing", "mls", "open house", "staging", "sign", "flyer"],
        "Travel": ["showing", "client meeting"],
    },
    "contractor": {
        "Supplies": ["lumber", "drywall", "concrete", "paint", "tile", "hardware"],
        "Equipment": ["drill", "saw", "compressor"],
    },
    "food": {
        "Supplies": ["ingredients", "produce", "meat", "dairy"],
        "Equipment": ["oven", "mixer", "fridge"],
    },
}


def _norm(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _match_bucket(text: str) -> Optional[str]:
    """
    Return best category by keyword hits (simple scoring).
    """
    if not text:
        return None

    scores: Dict[str, int] = {k: 0 for k in KEYWORDS.keys()}

    for cat, keys in KEYWORDS.items():
        for kw in keys:
            if kw in text:
                scores[cat] += 1

    best_cat = None
    best_score = 0
    for cat, sc in scores.items():
        if sc > best_score:
            best_score = sc
            best_cat = cat

    if best_cat and best_score > 0:
        return best_cat
    return None


def suggest_category(
    vendor: Optional[str] = None,
    ocr_text: Optional[str] = None,
    explanation: Optional[str] = None,
    business_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Returns:
        {
            "category": str|None,
            "confidence": float (0..1),
            "reasoning": str
        }

    Hierarchy:
        explanation > ocr_text > vendor
    """

    v = _norm(vendor)
    t = _norm(ocr_text)
    e = _norm(explanation)
    bt = _norm(business_type)

    # 1) Use business-type hinting to weight certain keywords
    # We do this by appending extra context tokens to explanation text.
    if bt in BUSINESS_TYPE_HINTS and e:
        for cat, kws in BUSINESS_TYPE_HINTS[bt].items():
            # If any hint keyword appears, bias that category heavily
            if any(_norm(k) in e for k in kws):
                return {
                    "category": cat,
                    "confidence": 0.90,
                    "reasoning": f"Matched business_type='{business_type}' hint in explanation",
                }

    # 2) Explanation-first
    cat = _match_bucket(e)
    if cat:
        return {"category": cat, "confidence": 0.85, "reasoning": "Matched keywords in explanation (highest priority)"}

    # 3) OCR text (invoice text / line items)
    cat = _match_bucket(t)
    if cat:
        return {"category": cat, "confidence": 0.70, "reasoning": "Matched keywords in OCR text"}

    # 4) Vendor fallback
    cat = _match_bucket(v)
    if cat:
        return {"category": cat, "confidence": 0.60, "reasoning": "Matched keywords in vendor"}

    # 5) No clue
    return {"category": None, "confidence": 0.0, "reasoning": "No category match found"}