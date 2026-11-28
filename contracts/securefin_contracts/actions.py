"""What the agent is allowed to propose. The agent never executes anything."""
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import RiskLevel
from .risk import RiskReason


class ToolName(str, Enum):
    GET_INVOICES = "get_invoices"
    GET_TRANSACTIONS = "get_transactions"
    CHECK_DUPLICATE = "check_duplicate"
    GET_RISK_SCORE = "get_risk_score"
    SEARCH_POLICIES = "search_policies"
    GENERATE_REPORT = "generate_report"
    CREATE_PAYMENT_REQUEST = "create_payment_request"


class CreatePaymentParams(BaseModel):
    """IBAN is never a parameter: it is always taken from the verified vendor record."""
    model_config = ConfigDict(extra="forbid")
    invoice_id: int = Field(gt=0)
    vendor_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="EGP", pattern=r"^[A-Z]{3}$")


class ProposedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: ToolName
    params: dict
    rationale: str = Field(default="", max_length=1000)


class ChatTurn(BaseModel):
    """One earlier message of the same conversation, oldest first. The agent reads it as context only (data)."""

    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(max_length=4000)
    mode: Literal["normal", "dry_run"] = "normal"
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)  # chat memory; empty = new conversation


class InvoiceAlert(BaseModel):
    """An invoice the assistant looked at that has a problem, with WHY, built by code from the data (never the LLM)."""

    invoice_id: int
    invoice_number: str | None = None
    vendor: str | None = None
    status: str | None = None          # e.g. FLAGGED
    level: RiskLevel | None = None     # from the risk service, when it was scored
    score: float | None = Field(default=None, ge=0, le=100)
    reasons: list[RiskReason] = Field(default_factory=list)  # rule hits + extraction issues, in plain words


class ChatResponse(BaseModel):
    answer: str
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    alerts: list[InvoiceAlert] = Field(default_factory=list)  # every flagged / risky invoice used, with its reasons
    sources: list[str] = Field(default_factory=list)          # read-only tools the answer is based on
