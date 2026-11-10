"""In-process stand-in for services/gateway, for tests only.

Follows the gateway's approval rules closely enough to test the api's side: it reads the
payment the way the gateway does (PaymentRequestInfo) and answers with the same shapes and
refusals (ApprovalRefused carries the HTTP status the real gateway would return).
"""

from decimal import Decimal

from app.gateway import ApprovalRefused, GatewayUnavailable
from app.store import DataStore
from securefin_contracts import (
    ApprovalRequest,
    ApprovalResult,
    ApprovalStatus,
    ExecuteCheckRequest,
    ExecuteCheckResult,
    InvoiceStatus,
    Role,
)

DUAL_APPROVAL_LIMIT = Decimal("10000")


class FakeGateway:
    def __init__(self, store: DataStore):
        self._store = store
        self.decisions: dict[int, list[ApprovalRequest]] = {}
        self.sent: list[ApprovalRequest | ExecuteCheckRequest] = []

    def _payment(self, payment_request_id: int):
        record = self._store.payment_request_by_id(payment_request_id)
        if record is None:
            raise ApprovalRefused(404, ["payment request not found"])
        return record.info()

    @staticmethod
    def _required(amount: Decimal, currency: str) -> int:
        return 2 if amount > DUAL_APPROVAL_LIMIT or currency != "EGP" else 1

    def submit_approval(self, req: ApprovalRequest) -> ApprovalResult:
        self.sent.append(req)
        payment = self._payment(req.payment_request_id)
        if req.approver_role is None or req.company_id is None:
            raise ApprovalRefused(403, ["approver role and company are required"])
        if req.company_id != payment.company_id:
            raise ApprovalRefused(403, ["approver belongs to a different company"])
        if req.approver_role not in {Role.ADMIN, Role.APPROVER}:
            raise ApprovalRefused(403, [f"role '{req.approver_role.value}' may not approve payments"])
        if req.approver_id == payment.creator_id:
            raise ApprovalRefused(403, ["maker-checker: the creator cannot approve their own payment request"])
        if payment.status != InvoiceStatus.PENDING_APPROVAL:
            raise ApprovalRefused(403, [f"payment request is {payment.status.value}, not awaiting approval"])
        existing = self.decisions.setdefault(req.payment_request_id, [])
        if any(d.approver_id == req.approver_id for d in existing):
            raise ApprovalRefused(403, ["this approver has already decided on this payment request"])

        existing.append(req)
        required = self._required(payment.amount, payment.currency)
        received = sum(d.approve for d in existing)
        if not req.approve:
            status, reasons = ApprovalStatus.REJECTED, ["rejected by approver"]
        else:
            status = ApprovalStatus.APPROVED if received >= required else ApprovalStatus.PENDING_APPROVAL
            reasons = []
        return ApprovalResult(payment_request_id=payment.id, status=status, approvals_received=received,
                              approvals_required=required, reasons=reasons)

    def execute_check(self, req: ExecuteCheckRequest) -> ExecuteCheckResult:
        self.sent.append(req)
        payment = self._payment(req.payment_request_id)
        decisions = self.decisions.get(req.payment_request_id, [])
        reasons = []
        if req.company_id != payment.company_id:
            return ExecuteCheckResult(allowed=False, reasons=["different company"])
        if payment.status != InvoiceStatus.PENDING_APPROVAL:
            reasons.append(f"payment request is {payment.status.value}, not awaiting execution")
        if any(not d.approve for d in decisions):
            reasons.append("payment request was rejected")
        required = self._required(payment.amount, payment.currency)
        received = sum(d.approve and d.approver_id != payment.creator_id for d in decisions)
        if received < required:
            reasons.append(f"{received} valid approval(s), {required} required")
        return ExecuteCheckResult(allowed=not reasons, reasons=reasons)


class DownGateway:
    """The gateway is unreachable or too slow."""

    def submit_approval(self, req):
        raise GatewayUnavailable("ConnectTimeout")

    def execute_check(self, req):
        raise GatewayUnavailable("ConnectTimeout")


def sql_store_with_sample_data(url: str | None = None):
    """SqlStore with the same sample data as seeded_store(): on an in-memory SQLite database, or,
    given a url, on a fresh schema in that database (all its tables are dropped first)."""
    from app.db import Base, make_engine
    from app.sql_store import SqlStore
    from app.store import seeded_store
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    if url:
        engine = make_engine(url)
        Base.metadata.drop_all(engine)
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    store = SqlStore(engine)
    store.load(seeded_store())
    return store
