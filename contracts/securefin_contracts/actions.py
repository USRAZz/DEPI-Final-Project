"""What the agent is allowed to propose. The agent never executes anything."""
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class ChatRequest(BaseModel):
    message: str = Field(max_length=4000)
    mode: Literal["normal", "dry_run"] = "normal"


class ChatResponse(BaseModel):
    answer: str
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
