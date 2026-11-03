from pydantic import BaseModel, Field

from .common import RiskLevel


class RiskRequest(BaseModel):
    invoice_id: int | None = None
    transaction_id: int | None = None
    features: dict = Field(default_factory=dict, description="Optional pre-computed features")


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
