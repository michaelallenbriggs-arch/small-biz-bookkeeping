from pydantic import BaseModel
from typing import Optional

class ReceiptParsed(BaseModel):
    vendor: Optional[str] = None
    date: Optional[str] = None
    total: Optional[float] = None
    tax: Optional[float] = None