"""Output of the quarantined extractor (SDD §5.1). Text outside this schema is discarded."""
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .common import Contract, InvoiceStatus


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(max_length=300)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)


class InvoiceData(BaseModel):
    # extra="forbid": anything the LLM adds outside the schema fails validation (prompt-injection defence)
    model_config = ConfigDict(extra="forbid")
    vendor: str = Field(max_length=200)
    invoice_no: str = Field(max_length=64)
    date: date
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="EGP", pattern=r"^[A-Z]{3}$")
    iban: str | None = Field(default=None, pattern=r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$")
    line_items: list[LineItem] = Field(default_factory=list)
    field_confidence: dict[str, float] = Field(default_factory=dict)


class ExtractResponse(BaseModel):
    """What services/extractor returns for one document (POST /v1/extract).

    data is None when the extracted fields do not fit InvoiceData (status NEEDS-REVIEW).
    issue_codes are stable codes (TOTAL_MISMATCH, POSSIBLE_DUPLICATE, ...) the api stores with the invoice;
    the risk service reads them through the api.
    """

    model_config = ConfigDict(extra="forbid")
    status: InvoiceStatus
    data: InvoiceData | None = None
    issue_codes: list[str] = Field(default_factory=list, max_length=20)
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)
    category: str | None = Field(default=None, max_length=64)


class InvoiceSource(str, Enum):
    UPLOAD = "upload"
    EMAIL = "email"
    ETA = "eta"


class Invoice(Contract):
    """The stored record, written by services/api. `fields` is the extractor's validated output."""

    id: int
    company_id: int
    vendor_id: int | None = None
    source: InvoiceSource
    status: InvoiceStatus
    fields: InvoiceData | None = None
    file_key: str = Field(max_length=500)
    # sha256 of the file bytes (lowercase hex). The database refuses the same file twice per company.
    file_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    duplicate_of: int | None = None
    category: str | None = Field(default=None, max_length=64)
    uploaded_by: int | None = None
    created_at: datetime
    # From ExtractResponse; used to build RiskFeatures. Stable codes such as TOTAL_MISMATCH, never free text.
    extraction_issues: list[str] = Field(default_factory=list, max_length=20)
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)
