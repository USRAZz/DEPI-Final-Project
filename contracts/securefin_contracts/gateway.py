from datetime import datetime

from pydantic import BaseModel, Field

from .actions import ProposedAction
from .common import Contract, Decision, EgyptianIBAN, Money, Role


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


class ApprovalPayload(Contract):
    """Exactly what an approver signs. Changing the amount or the account breaks the signature."""

    payment_request_id: int
    money: Money
    iban: EgyptianIBAN
    approver_id: int
    signed_at: datetime


class ApprovalRecord(BaseModel):
    payment_request_id: int
    approver_id: int
    approve: bool
    hmac_signature: str
    signed_at: datetime
