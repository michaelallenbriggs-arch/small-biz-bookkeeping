# app/services/categorizer_service.py
from __future__ import annotations

from typing import Any, Dict, Optional

from app.categories.rules import apply_category_rules
from app.categories.engine import suggest_category


# ------------------------------------------------------------------------------
# Categorizer Service (v1)
# ------------------------------------------------------------------------------
# Purpose:
# - Single entry point used by main.py (or parser) to get a category suggestion
# - Enforces hierarchy: deterministic rules first, then heuristic engine
# - Stable return shape:
#     {"category": str|None, "confidence": float, "reasoning": str, "source": str}
# ------------------------------------------------------------------------------


def categorize_purchase(
    *,
    vendor: Optional[str] = None,
    ocr_text: Optional[str] = None,
    explanation: Optional[str] = None,
    business_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Deterministic first:
        - vendor map
        - explanation keywords
        - OCR keywords
        - business type default

    Then heuristic engine fallback (engine honors hierarchy internally too)
    """

    # 1) deterministic rules
    rule_hit = apply_category_rules(
        vendor=vendor,
        explanation=explanation,
        ocr_text=ocr_text,
        business_type=business_type,
    )
    if rule_hit.get("category"):
        return {
            "category": rule_hit["category"],
            "confidence": float(rule_hit.get("confidence") or 0.0),
            "reasoning": rule_hit.get("reasoning") or "",
            "source": "rules",
        }

    # 2) heuristic engine fallback (engine honors hierarchy internally too)
    eng = suggest_category(
        vendor=vendor,
        ocr_text=ocr_text,
        explanation=explanation,
        business_type=business_type,
    )
    return {
        "category": eng.get("category"),
        "confidence": float(eng.get("confidence") or 0.0),
        "reasoning": eng.get("reasoning") or "",
        "source": "engine",
    }