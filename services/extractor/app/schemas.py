"""Data shapes for the invoice pipeline. When you push, compare field names with contracts/securefin_contracts/invoice.py."""
import os
import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

CATEGORIES = [c.strip() for c in os.getenv(
    "EXPENSE_CATEGORIES",
    "utilities,rent,office_supplies,software,travel,marketing,professional_services,inventory,maintenance,other",
).split(",") if c.strip()]
if "other" not in CATEGORIES:
    CATEGORIES.append("other")

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")  # Arabic-Indic + Persian digits
_CURRENCY = {"جنيه": "EGP", "جنيه مصري": "EGP", "ج.م": "EGP", "LE": "EGP", "L.E": "EGP", "LE.": "EGP", "دولار": "USD"}


def normalize_number(v):
    if v is None or isinstance(v, (int, float)):
        return v
    s = str(v).translate(_DIGITS).replace("٫", ".").replace("٬", "").replace("،", "").replace(",", "")
    s = re.sub(r"[^\d.\-]", "", s)  # drops currency symbols and spaces
    return float(s) if s not in ("", ".", "-") else None


def normalize_id(v):
    if v is None:
        return None
    return re.sub(r"\s+", "", str(v).translate(_DIGITS)).upper() or None


class LineItem(BaseModel):
    description: str
    quantity: float | None = None
    unit_price: float | None = None
    total: float | None = None

    @field_validator("quantity", "unit_price", "total", mode="before")
    @classmethod
    def _num(cls, v):
        return normalize_number(v)


class InvoiceFields(BaseModel):
    vendor_name: str
    invoice_number: str
    invoice_date: date | None = None
    due_date: date | None = None
    currency: str = "EGP"
    subtotal: float | None = None
    tax_amount: float | None = None
    total_amount: float
    iban: str | None = None
    tax_id: str | None = None
    language: Literal["ar", "en", "mixed"] | None = None
    line_items: list[LineItem] = Field(default_factory=list)

    @field_validator("subtotal", "tax_amount", "total_amount", mode="before")
    @classmethod
    def _num(cls, v):
        return normalize_number(v)

    @field_validator("iban", "tax_id", mode="before")
    @classmethod
    def _ids(cls, v):
        return normalize_id(v)

    @field_validator("invoice_number", mode="before")
    @classmethod
    def _inv_no(cls, v):
        return str(v).translate(_DIGITS).strip() if v is not None else v

    @field_validator("invoice_date", "due_date", mode="before")
    @classmethod
    def _dates(cls, v):
        return str(v).translate(_DIGITS).strip() if isinstance(v, str) else v

    @field_validator("currency", mode="before")
    @classmethod
    def _cur(cls, v):
        v = (str(v) if v else "EGP").strip()
        return _CURRENCY.get(v, v.upper())


class CategoryResult(BaseModel):
    category: str
    confidence: float = Field(ge=0, le=1)
    reason: str = ""

    @field_validator("category")
    @classmethod
    def _known(cls, v):
        v = v.strip().lower()
        return v if v in CATEGORIES else "other"


class ExtractionResult(BaseModel):
    status: Literal["READY", "FLAGGED", "FAILED"]
    fields: InvoiceFields | None = None
    category: CategoryResult | None = None
    issues: list[str] = Field(default_factory=list)
    # Stable codes (TOTAL_MISMATCH, ...) for the api to store with the invoice; the risk service reads them.
    issue_codes: list[str] = Field(default_factory=list)
    # Mean OCR engine confidence 0-1 over OCR'd pages; None when no OCR ran or the engine gives no score.
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)
    duplicate_of: str | None = None
    ocr_chars: int = 0
    usage: dict = Field(default_factory=dict)
    seconds: float = 0.0