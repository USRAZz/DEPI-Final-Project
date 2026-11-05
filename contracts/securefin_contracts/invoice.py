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
    duplicate_of: int | None = None
    category: str | None = Field(default=None, max_length=64)
    uploaded_by: int | None = None
    created_at: datetime
