from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from .actions import ProposedAction
from .common import ApprovalStatus, Decision, InvoiceStatus, Role


class AuthorizeRequest(BaseModel):
    user_id: int
    role: Role
    company_id: int
    action: ProposedAction
    request_id: str = Field(description="Idempotency / correlation id")


class GatewayDecision(BaseModel):
    decision: Decision
    reasons: list[str] = Field(default_factory=list)
    checks_passed: list[str] = Field(default_factory=list)
    risk_score: float | None = None
    required_approvers: int = 0
    audit_entry_id: int | None = None


class ApprovalRequest(BaseModel):
    payment_request_id: int
    approver_id: int
    approve: bool
    comment: str = Field(default="", max_length=500)
    approver_role: Role | None = Field(default=None, description="Set by the api from the session; gateway BLOCKs if missing")
    company_id: int | None = Field(default=None, description="Set by the api from the session; gateway BLOCKs if missing")


class ApprovalRecord(BaseModel):
    payment_request_id: int
    approver_id: int
    approve: bool
    hmac_signature: str
    signed_at: datetime


class PaymentRequestInfo(BaseModel):
    """Read model served by the api (GET /v1/payment-requests/{id}); the gateway never reads api tables."""

    id: int
    company_id: int
    creator_id: int
    invoice_id: int
    vendor_id: int
    amount: Decimal
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    status: InvoiceStatus
    created_at: datetime


class ApprovalResult(BaseModel):
    payment_request_id: int
    status: ApprovalStatus
    approvals_received: int = Field(ge=0)
    approvals_required: int = Field(ge=0)
    reasons: list[str] = Field(default_factory=list)
    audit_entry_id: int | None = None


class ExecuteCheckRequest(BaseModel):
    payment_request_id: int
    requested_by: int
    company_id: int


class ExecuteCheckResult(BaseModel):
    allowed: bool
    reasons: list[str] = Field(default_factory=list)
    audit_entry_id: int | None = None
