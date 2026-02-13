# app/services/storage_service.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # project/app -> project
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
RECEIPTS_DIR = os.path.join(DATA_DIR, "receipts")

os.makedirs(RECEIPTS_DIR, exist_ok=True)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _receipt_path(receipt_id: str) -> str:
    return os.path.join(RECEIPTS_DIR, f"{receipt_id}.json")


def _safe_json_dump(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _safe_json_load(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _upgrade_payload(payload: Dict[str, Any], receipt_id: str) -> Dict[str, Any]:
    """
    Backward-compat shim:
    - Older receipts may have ocr_text/ocr_status at top-level instead of nested `ocr`.
    - Ensure flags/needs_review exist.
    - Ensure id exists.
    """
    if "id" not in payload:
        payload["id"] = receipt_id

    # Upgrade OCR structure if needed
    if "ocr" not in payload or not isinstance(payload.get("ocr"), dict):
        payload["ocr"] = {
            "ocr_text": payload.get("ocr_text", ""),
            "ocr_status": payload.get("ocr_status", "unknown"),
            "ocr_source": payload.get("ocr_source", "unknown"),
            "ocr_confidence": payload.get("ocr_confidence", 0.0),
        }

    payload.setdefault("flags", [])
    payload.setdefault("needs_review", False)
    payload.setdefault("filename", payload.get("source_filename", ""))

    return payload


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def save_receipt_payload(receipt_id: str, filename: str, payload: Dict[str, Any]) -> str:
    """
    Saves the canonical receipt payload to disk.
    Returns the path of the JSON file (saved_path).
    """
    os.makedirs(RECEIPTS_DIR, exist_ok=True)

    # Make sure payload carries core identifiers
    payload = dict(payload)
    payload.setdefault("id", str(receipt_id))
    payload.setdefault("filename", filename)

    path = _receipt_path(str(receipt_id))
    tmp_path = path + ".tmp"

    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(_safe_json_dump(payload))

    # atomic-ish replace
    os.replace(tmp_path, path)
    return path


def load_receipt_payload(receipt_id: str) -> Dict[str, Any]:
    """
    Loads a canonical receipt payload from disk (and upgrades older formats).
    Raises FileNotFoundError if missing.
    """
    path = _receipt_path(str(receipt_id))
    if not os.path.exists(path):
        raise FileNotFoundError(f"Receipt payload not found: {receipt_id}")

    payload = _safe_json_load(path)
    payload = _upgrade_payload(payload, str(receipt_id))
    return payload


def list_receipt_ids(limit: int = 50, newest_first: bool = True) -> List[str]:
    """
    Lists receipt IDs based on files present in data/receipts.
    """
    if not os.path.exists(RECEIPTS_DIR):
        return []

    ids: List[str] = []
    for name in os.listdir(RECEIPTS_DIR):
        if name.endswith(".json"):
            ids.append(name[:-5])  # strip .json

    # Sort by mtime for "newest first"
    if newest_first:
        ids.sort(key=lambda rid: os.path.getmtime(_receipt_path(rid)), reverse=True)
    else:
        ids.sort()

    return ids[: max(1, limit)]


def delete_receipt_payload(receipt_id: str) -> bool:
    """
    Deletes a receipt payload JSON file. Returns True if deleted.
    """
    path = _receipt_path(str(receipt_id))
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def purge_all_receipts() -> int:
    """
    Deletes all receipt payload files. Returns count deleted.
    Useful for local testing only.
    """
    if not os.path.exists(RECEIPTS_DIR):
        return 0

    count = 0
    for name in os.listdir(RECEIPTS_DIR):
        if name.endswith(".json"):
            os.remove(os.path.join(RECEIPTS_DIR, name))
            count += 1
    return count