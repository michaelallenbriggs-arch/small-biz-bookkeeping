from __future__ import annotations

import re
from typing import Dict, Optional, List


# ============================================================
# Vendor aliases (normalization only — NO categories here)
# ============================================================

VENDOR_ALIASES: Dict[str, List[str]] = {
    "LOWES": ["LOWE'S", "LOWES"],
    "HOME DEPOT": ["HOME DEPOT", "HOMEDP", "HD"],
    "WALMART": ["WALMART", "WAL-MART"],
    "TARGET": ["TARGET"],
    "COSTCO": ["COSTCO"],
    "AUTOZONE": ["AUTOZONE"],
    "ACE HARDWARE": ["ACE HARDWARE", "ACE HDWR"],
    "HARBOR FREIGHT": ["HARBOR FREIGHT"],
    "GRAINGER": ["GRAINGER"],
    "FASTENAL": ["FASTENAL"],
    "O REILLY": ["O'REILLY", "OREILLY"],
    "NAPA": ["NAPA"],
    "PEP BOYS": ["PEP BOYS"],

    "EXXON": ["EXXON"],
    "SUNOCO": ["SUNOCO"],
    "ROYAL FARMS": ["ROYAL FARMS"],
    "LOVES": ["LOVE'S", "LOVES"],
    "TA TRAVEL CENTER": ["TA", "TRAVEL CENTER"],
    "SPEEDWAY": ["SPEEDWAY"],

    "SYSCO": ["SYSCO"],
    "US FOODS": ["US FOODS"],
    "RESTAURANT DEPOT": ["RESTAURANT DEPOT"],

    "STAPLES": ["STAPLES"],
    "OFFICE DEPOT": ["OFFICE DEPOT"],
    "ADOBE": ["ADOBE"],
    "QUICKBOOKS": ["QUICKBOOKS", "INTUIT"],

    "TRACTOR SUPPLY": ["TRACTOR SUPPLY", "TSC"],
    "AGWAY": ["AGWAY"],
    "SOUTHERN STATES": ["SOUTHERN STATES"],
    "NUTRIEN": ["NUTRIEN"],
    "PERDUE FARMS": ["PERDUE"],
    "ALLEN HARIM": ["ALLEN HARIM"],
    "TYSON FOODS": ["TYSON"],

    "KUBOTA": ["KUBOTA"],
    "CASE IH": ["CASE IH"],
    "FEED MILL": ["FEED MILL"],
    "DELMARVA VET SUPPLY": ["DELMARVA VET"],

    "FERGUSON": ["FERGUSON"],
    "JOHNSTONE SUPPLY": ["JOHNSTONE"],
    "SUPPLY HOUSE": ["SUPPLYHOUSE"],
    "HD SUPPLY": ["HD SUPPLY"],

    "RHEEM": ["RHEEM"],
    "TRANE": ["TRANE"],
    "CARRIER": ["CARRIER"],

    "SHERWIN WILLIAMS": ["SHERWIN", "SHERWIN-WILLIAMS"],
    "BENJAMIN MOORE": ["BENJAMIN MOORE"],

    "SITEONE": ["SITEONE"],
    "STIHL": ["STIHL"],
    "HUSQVARNA": ["HUSQVARNA"],
    "ECHO": ["ECHO"],
    "EXMARK": ["EXMARK"],
    "TORO": ["TORO"],

    "ULINE": ["ULINE"],

    "PETSMART": ["PETSMART"],
    "PETCO": ["PETCO"],
    "CHEWY": ["CHEWY"],

    "ROGUE FITNESS": ["ROGUE"],
    "REP FITNESS": ["REP FITNESS"],
    "MINDBODY": ["MINDBODY"],

    "UNIFORM ADVANTAGE": ["UNIFORM ADVANTAGE"],
    "CARE.COM": ["CARE.COM"],

    "SAM'S CLUB": ["SAM'S CLUB", "SAMS CLUB"],
    "CHEMICAL GUYS": ["CHEMICAL GUYS"],
    "DETAIL KING": ["DETAIL KING"],
}


# ============================================================
# Vendor → Category mapping (BOOKKEEPING LOGIC)
# ============================================================

VENDOR_CATEGORY_MAP: Dict[str, str] = {

    # ---------- Repairs / Maintenance ----------
    "LOWES": "Repairs & Maintenance",
    "HOME DEPOT": "Repairs & Maintenance",
    "ACE HARDWARE": "Repairs & Maintenance",
    "HARBOR FREIGHT": "Repairs & Maintenance",
    "GRAINGER": "Repairs & Maintenance",
    "FASTENAL": "Repairs & Maintenance",
    "FERGUSON": "Repairs & Maintenance",
    "JOHNSTONE SUPPLY": "Repairs & Maintenance",
    "HD SUPPLY": "Repairs & Maintenance",
    "SUPPLY HOUSE": "Repairs & Maintenance",

    # ---------- Fuel ----------
    "EXXON": "Fuel",
    "SUNOCO": "Fuel",
    "LOVES": "Fuel",
    "TA TRAVEL CENTER": "Fuel",
    "SPEEDWAY": "Fuel",

    # ---------- Office / Software ----------
    "STAPLES": "Office Supplies",
    "OFFICE DEPOT": "Office Supplies",
    "ULINE": "Office Supplies",
    "ADOBE": "Software",
    "QUICKBOOKS": "Software",
    "MINDBODY": "Software",

    # ---------- Vehicle ----------
    "AUTOZONE": "Vehicle Expenses",
    "O REILLY": "Vehicle Expenses",
    "NAPA": "Vehicle Expenses",
    "PEP BOYS": "Vehicle Expenses",

    # ---------- Meals ----------
    "ROYAL FARMS": "Meals",
    "SYSCO": "Meals",
    "US FOODS": "Meals",
    "RESTAURANT DEPOT": "Meals",

    # ---------- Farm / Ag ----------
    "TRACTOR SUPPLY": "Farm Supplies",
    "AGWAY": "Farm Supplies",
    "SOUTHERN STATES": "Farm Supplies",
    "NUTRIEN": "Farm Supplies",
    "FEED MILL": "Farm Supplies",
    "DELMARVA VET SUPPLY": "Farm Supplies",
    "PERDUE FARMS": "Farm Supplies",
    "ALLEN HARIM": "Farm Supplies",
    "TYSON FOODS": "Farm Supplies",

    # ---------- Equipment ----------
    "KUBOTA": "Equipment",
    "CASE IH": "Equipment",
    "STIHL": "Equipment",
    "HUSQVARNA": "Equipment",
    "ECHO": "Equipment",
    "EXMARK": "Equipment",
    "TORO": "Equipment",

    # ---------- Pets ----------
    "PETSMART": "Animal Expenses",
    "PETCO": "Animal Expenses",
    "CHEWY": "Animal Expenses",

    # ---------- Fitness ----------
    "ROGUE FITNESS": "Equipment",
    "REP FITNESS": "Equipment",

    # ---------- Uniform / Labor ----------
    "UNIFORM ADVANTAGE": "Uniforms",
    "CARE.COM": "Contract Labor",

    # ---------- Retail ----------
    "WALMART": "Office Supplies",
    "TARGET": "Office Supplies",
    "COSTCO": "Office Supplies",
    "SAM'S CLUB": "Office Supplies",
}


# ============================================================
# Utilities
# ============================================================

def _normalize(text: str) -> str:
    return re.sub(r"[^A-Z0-9 ]+", "", text.upper()).strip()


def empty() -> dict:
    return {
        "vendor": None,
        "vendor_confidence": 0.0,
        "vendor_reasoning": "",
        "vendor_source": None,

        "category": None,
        "category_confidence": 0.0,
        "category_reasoning": "",
        "category_source": None,
    }


# ============================================================
# Main pipeline function
# ============================================================

def detect_vendor(text: str) -> dict:
    if not text:
        return empty()

    normalized_text = _normalize(text)

    for canonical, aliases in VENDOR_ALIASES.items():
        for alias in aliases:
            if _normalize(alias) in normalized_text:
                category = VENDOR_CATEGORY_MAP.get(canonical)

                return {
                    "vendor": canonical,
                    "vendor_confidence": 0.95,
                    "vendor_reasoning": f"Matched alias '{alias}'",
                    "vendor_source": "alias_match",

                    "category": category,
                    "category_confidence": 0.95 if category else 0.0,
                    "category_reasoning": (
                        "Mapped from vendor" if category else "Vendor not mapped"
                    ),
                    "category_source": "vendor_map" if category else None,
                }

    return empty()