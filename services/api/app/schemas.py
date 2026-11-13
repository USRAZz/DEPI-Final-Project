"""Response shapes for the frontend: contract models grouped per screen.

These are views, not new shared shapes, so they live here and not in contracts/.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from securefin_contracts import ApprovalStatus, BankAccount, Money, RiskScore, User, Vendor

from .models import PaymentRecord


class AccountView(BankAccount):
    times_paid: int


class PendingRow(BaseModel):
    request: PaymentRecord
    vendor: Vendor
    created_by: User
    risk: RiskScore | None


class DashboardView(BaseModel):
    month_spend: Money
    invoices_paid: int
    pending_count: int
    above_limit_count: int
    flagged_count: int
    on_hold_count: int
    pending: list[PendingRow]


class ApprovalView(BaseModel):
    approver: User
    approved: bool
    at: datetime


class ApprovalState(BaseModel):
    """The gateway's latest answer for this request. Before the first approval, required is the api's estimate."""

    status: ApprovalStatus
    approvals_received: int
    approvals_required: int
    reasons: list[str] = Field(default_factory=list)


class PaymentRequestView(BaseModel):
    request: PaymentRecord
    vendor: Vendor
    account: AccountView
    created_by: User
    risk: RiskScore | None
    approval: ApprovalState
    approvals: list[ApprovalView]


class BankChangeView(BaseModel):
    vendor: Vendor
    current: AccountView | None
    proposed: AccountView | None
    requested_by: User | None


class ApprovalIn(BaseModel):
    # Role and company come from the session, never from the body.
    model_config = ConfigDict(extra="forbid")

    approved: bool
    comment: str = Field(default="", max_length=500)


class ExecutionView(BaseModel):
    request: PaymentRecord
    executed: bool
    reasons: list[str] = Field(default_factory=list)
