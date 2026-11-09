from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from .common import RiskLevel


class RiskRequest(BaseModel):
    invoice_id: int | None = None
    transaction_id: int | None = None
    features: dict = Field(default_factory=dict, description="Optional pre-computed features")


class RiskFeatures(BaseModel):
    """Facts about one invoice, computed and served by services/api (GET /v1/invoices/{id}/risk-features).

    Only booleans and numbers: raw bank details never leave the api. None means "not known yet",
    which scores the same as False. Add fields with a default; never rename or remove one.
    """

    model_config = ConfigDict(extra="forbid")
    duplicate_detected: bool | None = None  # same company + vendor + invoice number as an earlier invoice
    invoice_total_mismatch: bool | None = None  # extractor found subtotal + tax != total
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)  # lowest field confidence from the extractor
    invoice_total_egp: Decimal | None = Field(default=None, ge=0)
    bank_account_mismatch: bool | None = None  # IBAN on the invoice differs from the vendor's verified account
    vendor_change_pending: bool | None = None  # vendor bank account is still on hold


class ShapReason(BaseModel):
    feature: str
    value: float | str
    contribution: float


class RiskScore(BaseModel):
    score: float = Field(ge=0, le=100)
    level: RiskLevel
    rule_hits: list[str] = Field(default_factory=list)
    shap_reasons: list[ShapReason] = Field(default_factory=list)
    model_version: str = "rules-v0"
