"""Response shapes for the frontend: contract models grouped per screen.

These are views, not new shared shapes, so they live here and not in contracts/.
"""

from datetime import datetime

from pydantic import BaseModel
from securefin_contracts import BankAccount, GatewayDecision, Money, RiskScore, User, Vendor

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
    signed_at: datetime


class PaymentRequestView(BaseModel):
    request: PaymentRecord
    vendor: Vendor
    account: AccountView
    created_by: User
    risk: RiskScore | None
    gateway: GatewayDecision
    approvals: list[ApprovalView]


class BankChangeView(BaseModel):
    vendor: Vendor
    current: AccountView | None
    proposed: AccountView | None
    requested_by: User | None


class ApprovalIn(BaseModel):
    approved: bool
