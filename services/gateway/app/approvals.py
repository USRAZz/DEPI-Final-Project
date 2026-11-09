"""Approval rules: maker-checker, one or two approvers, HMAC-signed approvals, expiry.

Pure functions: no database and no web framework. The endpoint layer loads the payment request
from the api and the stored approvals from the gateway tables, calls these, then stores the result.
Anything wrong (missing key, bad signature, bad input) means "not approved" (fail closed).
"""
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal

from securefin_contracts import (
    ApprovalRecord,
    ApprovalRequest,
    ApprovalResult,
    ApprovalStatus,
    ExecuteCheckRequest,
    ExecuteCheckResult,
    InvoiceStatus,
    PaymentRequestInfo,
)

from .policy import GatewayPolicy

KEY_ENV = "APPROVAL_HMAC_KEY"
MIN_KEY_BYTES = 32


class ApprovalKeyError(RuntimeError):
    """The signing key is missing or too short."""


class ApprovalDenied(Exception):  # noqa: N818  (a business outcome, not an error class name)
    """The approval is refused; nothing is recorded. `reasons` explain why."""

    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def load_hmac_key() -> bytes:
    key = os.environ.get(KEY_ENV, "").encode()
    if len(key) < MIN_KEY_BYTES:
        raise ApprovalKeyError(f"{KEY_ENV} must be set and at least {MIN_KEY_BYTES} bytes")
    return key


def _amount_text(amount: Decimal) -> str:
    return format(amount.normalize(), "f")  # 25000.50 and 25000.5 sign the same


def sign_approval(key: bytes, payment: PaymentRequestInfo, approver_id: int, approve: bool,
                  signed_at: datetime) -> str:
    """HMAC-SHA256 over the exact payment details and the decision."""
    if len(key) < MIN_KEY_BYTES:
        raise ApprovalKeyError("key too short")
    payload = {
        "payment_request_id": payment.id,
        "company_id": payment.company_id,
        "invoice_id": payment.invoice_id,
        "vendor_id": payment.vendor_id,
        "amount": _amount_text(payment.amount),
        "currency": payment.currency,
        "approver_id": approver_id,
        "approve": approve,
        "signed_at": signed_at.isoformat(),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()


def signature_valid(key: bytes, payment: PaymentRequestInfo, record: ApprovalRecord) -> bool:
    if record.payment_request_id != payment.id:
        return False
    expected = sign_approval(key, payment, record.approver_id, record.approve, record.signed_at)
    return hmac.compare_digest(expected, record.hmac_signature)


def _expiry(policy: GatewayPolicy) -> timedelta:
    return timedelta(hours=policy.defaults.approvals.approval_expiry_hours)


def _counted_approvers(key: bytes, payment: PaymentRequestInfo, records: list[ApprovalRecord],
                       policy: GatewayPolicy, now: datetime) -> set[int]:
    """Distinct approvers whose approval is genuine, unexpired and still matches the payment."""
    return {
        r.approver_id for r in records
        if r.approve and now - r.signed_at <= _expiry(policy) and signature_valid(key, payment, r)
    }


def submit_approval(req: ApprovalRequest, payment: PaymentRequestInfo, existing: list[ApprovalRecord],
                    policy: GatewayPolicy, key: bytes, now: datetime) -> tuple[ApprovalResult, ApprovalRecord | None]:
    """Apply one approve/reject. Returns the result and the record to store (None if nothing to store)."""
    if req.approver_role is None or req.company_id is None:
        raise ApprovalDenied(["approver role and company are required"])
    if req.payment_request_id != payment.id:
        raise ApprovalDenied(["payment request mismatch"])
    if req.company_id != payment.company_id:
        raise ApprovalDenied(["approver belongs to a different company"])
    if req.approver_role not in policy.defaults.approvals.approver_roles:
        raise ApprovalDenied([f"role '{req.approver_role.value}' may not approve payments"])
    if req.approver_id == payment.creator_id:
        raise ApprovalDenied(["maker-checker: the creator cannot approve their own payment request"])
    if payment.status != InvoiceStatus.PENDING_APPROVAL:
        raise ApprovalDenied([f"payment request is {payment.status.value}, not awaiting approval"])
    if any(r.approver_id == req.approver_id for r in existing):
        raise ApprovalDenied(["this approver has already decided on this payment request"])

    required = policy.required_approvers(payment.amount, payment.currency)
    if any(not r.approve and signature_valid(key, payment, r) for r in existing):
        raise ApprovalDenied(["payment request was already rejected"])
    if now - payment.created_at > _expiry(policy):
        return ApprovalResult(payment_request_id=payment.id, status=ApprovalStatus.EXPIRED,
                              approvals_received=len(_counted_approvers(key, payment, existing, policy, now)),
                              approvals_required=required, reasons=["approval window has expired"]), None

    record = ApprovalRecord(payment_request_id=payment.id, approver_id=req.approver_id, approve=req.approve,
                            hmac_signature=sign_approval(key, payment, req.approver_id, req.approve, now),
                            signed_at=now)
    if not req.approve:
        return ApprovalResult(payment_request_id=payment.id, status=ApprovalStatus.REJECTED,
                              approvals_received=len(_counted_approvers(key, payment, existing, policy, now)),
                              approvals_required=required, reasons=["rejected by approver"]), record
    received = len(_counted_approvers(key, payment, [*existing, record], policy, now))
    status = ApprovalStatus.APPROVED if received >= required else ApprovalStatus.PENDING_APPROVAL
    return ApprovalResult(payment_request_id=payment.id, status=status, approvals_received=received,
                          approvals_required=required), record


def execute_check(req: ExecuteCheckRequest, payment: PaymentRequestInfo, records: list[ApprovalRecord],
                  policy: GatewayPolicy, key: bytes, now: datetime) -> ExecuteCheckResult:
    """May the api execute this payment right now? Recomputes every signature from the CURRENT payment data."""
    reasons: list[str] = []
    if req.payment_request_id != payment.id:
        return ExecuteCheckResult(allowed=False, reasons=["payment request mismatch"])
    if req.company_id != payment.company_id:
        return ExecuteCheckResult(allowed=False, reasons=["different company"])
    if payment.status != InvoiceStatus.PENDING_APPROVAL:
        reasons.append(f"payment request is {payment.status.value}, not awaiting execution")
    if any(not r.approve for r in records):
        reasons.append("payment request was rejected")
    if any(not signature_valid(key, payment, r) for r in records):
        reasons.append("an approval does not match the current payment details (possible tampering)")
    counted = _counted_approvers(key, payment, records, policy, now)
    if payment.creator_id in counted:
        reasons.append("maker-checker: the creator is among the approvers")
        counted.discard(payment.creator_id)
    required = policy.required_approvers(payment.amount, payment.currency)
    if len(counted) < required:
        reasons.append(f"{len(counted)} valid approval(s), {required} required")
    return ExecuteCheckResult(allowed=not reasons, reasons=reasons)
