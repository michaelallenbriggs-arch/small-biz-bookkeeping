# app/schemas.py
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# OCR
# -----------------------------------------------------------------------------

class OCRMeta(BaseModel):
    ocr_text: str = ""
    ocr_status: str = "unknown"   # "success", "low_confidence", etc
    ocr_source: str = "unknown"   # "tesseract", "raw", "pdf", etc
    ocr_confidence: float = 0.0


# -----------------------------------------------------------------------------
# Parsed (raw extraction output)
# Keep this tolerant: parser evolves, OCR varies, receipts are chaos.
# -----------------------------------------------------------------------------

class ReceiptParsed(BaseModel):
    # core fields
    vendor: Optional[str] = None
    vendor_confidence: float = 0.0
    vendor_reasoning: str = ""
    vendor_source: Optional[str] = None

    date: Optional[str] = None               # keep as string in v1 ("YYYY-MM-DD" or whatever you parse)
    date_confidence: float = 0.0
    date_reasoning: str = ""

    total: Optional[float] = None
    total_confidence: float = 0.0
    total_reasoning: str = ""

    tax: Optional[float] = None

    # categorization
    category: Optional[str] = None
    category_confidence: float = 0.0
    category_reasoning: str = ""

    # business context inputs (optional but useful)
    explanation: Optional[str] = None
    business_type: Optional[str] = None
    business_state: Optional[str] = None

    # review + flags
    flags: List[str] = Field(default_factory=list)
    needs_review: bool = False

    # if you later add line items / memo / address etc, it won't break
    extra: Dict[str, Any] = Field(default_factory=dict)


# -----------------------------------------------------------------------------
# Normalized (canonical output accountants care about)
# -----------------------------------------------------------------------------

class ReceiptNormalized(BaseModel):
    vendor: Optional[str] = None
    vendor_confidence: float = 0.0
    vendor_reasoning: str = ""
    vendor_source: Optional[str] = None

    date: Optional[str] = None
    date_confidence: float = 0.0
    date_reasoning: str = ""

    total: Optional[float] = None
    total_confidence: float = 0.0
    total_reasoning: str = ""

    tax: Optional[float] = None

    category: Optional[str] = None
    category_confidence: float = 0.0
    category_reasoning: str = ""

    explanation: Optional[str] = None
    business_type: Optional[str] = None
    business_state: Optional[str] = None

    # review state also appears here so UI doesn't need to look in 3 places
    flags: List[str] = Field(default_factory=list)
    needs_review: bool = False


# -----------------------------------------------------------------------------
# Responses
# -----------------------------------------------------------------------------

class UploadResponse(BaseModel):
    id: str
    filename: str
    # This is the saved JSON payload path (canonical). Don't confuse with the uploaded file path.
    saved_path: str

    ocr: OCRMeta

    # Keep these typed. If you return dicts, FastAPI/Pydantic will coerce them.
    parsed: ReceiptParsed | Dict[str, Any]
    normalized: ReceiptNormalized | Dict[str, Any]

    flags: List[str] = Field(default_factory=list)
    needs_review: bool = False


# -----------------------------------------------------------------------------
# Batch upload
# -----------------------------------------------------------------------------

class BatchUploadResult(BaseModel):
    filename: str
    receipt_id: Optional[str] = None
    status: Literal["success", "failed"]
    error: Optional[str] = None

    ocr: Optional[OCRMeta] = None
    flags: List[str] = Field(default_factory=list)
    needs_review: bool = False

    parsed: Optional[ReceiptParsed] = None
    normalized: Optional[ReceiptNormalized] = None


class BatchUploadResponse(BaseModel):
    batch_id: str
    total: int
    processed: int
    results: List[BatchUploadResult] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Review patch (accountant override)
# -----------------------------------------------------------------------------

class ReceiptReviewPatch(BaseModel):
    """
    Only send what you want to fix. Everything is Optional on purpose.
    """
    vendor: Optional[str] = None
    date: Optional[str] = None
    total: Optional[float] = None
    tax: Optional[float] = None
    category: Optional[str] = None

    # optional: if your system accepts memo overrides
    explanation: Optional[str] = None


# -----------------------------------------------------------------------------
# Backward/compat helpers (optional, but nice if old endpoints reference them)
# -----------------------------------------------------------------------------

class ReceiptListItem(BaseModel):
    id: str
    filename: Optional[str] = None
    flags: List[str] = Field(default_factory=list)
    needs_review: bool = False



    

