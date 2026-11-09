from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from securefin_contracts import (
    ApprovalRequest,
    ApprovalResult,
    ApprovalStatus,
    AuditEvent,
    ExecuteCheckRequest,
    ExecuteCheckResult,
    InvoiceStatus,
    PaymentRequestInfo,
    Role,
)


def test_old_approval_request_still_valid():
    # additive change: a payload built before the new fields existed must still parse
    r = ApprovalRequest(payment_request_id=1, approver_id=2, approve=True)
    assert r.approver_role is None and r.company_id is None


def test_approval_request_new_fields():
    r = ApprovalRequest(payment_request_id=1, approver_id=2, approve=False, approver_role="approver", company_id=3)
    assert r.approver_role is Role.APPROVER and r.company_id == 3


def test_old_audit_event_still_valid():
    e = AuditEvent(user_id=1, action="login", source_service="gateway")
    assert e.company_id is None


def test_payment_request_info_roundtrip():
    p = PaymentRequestInfo(id=1, company_id=1, creator_id=7, invoice_id=2, vendor_id=3, amount=Decimal("25000.50"),
                           currency="EGP", status=InvoiceStatus.PENDING_APPROVAL, created_at=datetime.now(UTC))
    assert PaymentRequestInfo.model_validate_json(p.model_dump_json()) == p


def test_payment_request_info_rejects_bad_currency():
    with pytest.raises(ValidationError):
        PaymentRequestInfo(id=1, company_id=1, creator_id=7, invoice_id=2, vendor_id=3, amount=Decimal("1"),
                           currency="egp", status=InvoiceStatus.VALIDATED, created_at=datetime.now(UTC))


def test_approval_result_statuses():
    assert {s.value for s in ApprovalStatus} == {"PENDING_APPROVAL", "APPROVED", "REJECTED", "EXPIRED"}
    r = ApprovalResult(payment_request_id=1, status="APPROVED", approvals_received=2, approvals_required=2)
    assert r.reasons == [] and r.audit_entry_id is None


def test_approval_result_rejects_negative_counts():
    with pytest.raises(ValidationError):
        ApprovalResult(payment_request_id=1, status="APPROVED", approvals_received=-1, approvals_required=1)


def test_execute_check_models():
    assert ExecuteCheckRequest(payment_request_id=1, requested_by=2, company_id=3).requested_by == 2
    r = ExecuteCheckResult(allowed=False, reasons=["approval payload changed"])
    assert r.allowed is False
