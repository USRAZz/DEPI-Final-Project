from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.approvals import (
    ApprovalDenied,
    ApprovalKeyError,
    execute_check,
    load_hmac_key,
    sign_approval,
    signature_valid,
    submit_approval,
)
from app.policy import load_gateway_policy
from securefin_contracts import (
    ApprovalRecord,
    ApprovalRequest,
    ApprovalStatus,
    ExecuteCheckRequest,
    InvoiceStatus,
    PaymentRequestInfo,
    Role,
)

KEY = b"k" * 32
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
POLICY = load_gateway_policy()


def pay(**kw) -> PaymentRequestInfo:
    base = {"id": 1, "company_id": 1, "creator_id": 7, "invoice_id": 2, "vendor_id": 3, "amount": Decimal("500"),
            "currency": "EGP", "status": InvoiceStatus.PENDING_APPROVAL, "created_at": NOW - timedelta(hours=1)}
    return PaymentRequestInfo(**{**base, **kw})


def req(approver_id=10, approve=True, role=Role.APPROVER, company_id=1, pid=1) -> ApprovalRequest:
    return ApprovalRequest(payment_request_id=pid, approver_id=approver_id, approve=approve,
                           approver_role=role, company_id=company_id)


def submit(request, payment=None, existing=None, now=NOW):
    return submit_approval(request, payment or pay(), existing or [], POLICY, KEY, now)


def approved_by(payment, approver_id, at=NOW, approve=True):
    return ApprovalRecord(payment_request_id=payment.id, approver_id=approver_id, approve=approve,
                          hmac_signature=sign_approval(KEY, payment, approver_id, approve, at), signed_at=at)


def check(payment, records, now=NOW, company=1):
    return execute_check(ExecuteCheckRequest(payment_request_id=payment.id, requested_by=7, company_id=company),
                         payment, records, POLICY, KEY, now)


# ---- submit_approval: refusals ----------------------------------------------------------

@pytest.mark.parametrize(("request_", "fragment"), [
    (ApprovalRequest(payment_request_id=1, approver_id=10, approve=True), "required"),
    (req(role=Role.VIEWER), "may not approve"),
    (req(role=Role.ACCOUNTANT), "may not approve"),
    (req(company_id=2), "different company"),
    (req(approver_id=7), "maker-checker"),            # 7 is the creator
    (req(pid=99), "mismatch"),
])
def test_refusals(request_, fragment):
    with pytest.raises(ApprovalDenied) as e:
        submit(request_)
    assert fragment in e.value.reasons[0]


def test_creator_blocked_even_as_admin():
    with pytest.raises(ApprovalDenied) as e:
        submit(req(approver_id=7, role=Role.ADMIN))
    assert "maker-checker" in e.value.reasons[0]


def test_cannot_decide_twice():
    p = pay()
    with pytest.raises(ApprovalDenied):
        submit(req(approver_id=10), p, [approved_by(p, 10)])


@pytest.mark.parametrize("status", [InvoiceStatus.PAID_SIMULATED, InvoiceStatus.REJECTED, InvoiceStatus.VALIDATED])
def test_not_awaiting_approval(status):
    with pytest.raises(ApprovalDenied):
        submit(req(), pay(status=status))


def test_already_rejected_request_cannot_be_approved():
    p = pay()
    with pytest.raises(ApprovalDenied) as e:
        submit(req(approver_id=11), p, [approved_by(p, 10, approve=False)])
    assert "already rejected" in e.value.reasons[0]


# ---- submit_approval: outcomes ----------------------------------------------------------

def test_one_approver_enough_for_small_amount():
    res, rec = submit(req())
    assert res.status is ApprovalStatus.APPROVED and res.approvals_received == 1 and res.approvals_required == 1
    assert rec is not None and signature_valid(KEY, pay(), rec)


def test_big_amount_needs_two_distinct_approvers():
    p = pay(amount=Decimal("25000"))
    res1, rec1 = submit(req(approver_id=10), p)
    assert res1.status is ApprovalStatus.PENDING_APPROVAL and res1.approvals_required == 2
    res2, _ = submit(req(approver_id=11), p, [rec1])
    assert res2.status is ApprovalStatus.APPROVED and res2.approvals_received == 2


def test_threshold_exact_amount_needs_one():
    res, _ = submit(req(), pay(amount=Decimal("10000")))
    assert res.approvals_required == 1


def test_foreign_currency_needs_two():
    res, _ = submit(req(), pay(currency="USD", amount=Decimal("5")))
    assert res.approvals_required == 2 and res.status is ApprovalStatus.PENDING_APPROVAL


def test_reject_is_recorded_and_stops():
    res, rec = submit(req(approve=False))
    assert res.status is ApprovalStatus.REJECTED and rec is not None and rec.approve is False


def test_expired_request_records_nothing():
    old = pay(created_at=NOW - timedelta(hours=73))
    res, rec = submit(req(), old)
    assert res.status is ApprovalStatus.EXPIRED and rec is None


def test_just_inside_expiry_window_ok():
    res, rec = submit(req(), pay(created_at=NOW - timedelta(hours=72)))
    assert res.status is ApprovalStatus.APPROVED and rec is not None


def test_forged_prior_approval_is_not_counted():
    p = pay(amount=Decimal("25000"))
    forged = ApprovalRecord(payment_request_id=1, approver_id=10, approve=True, hmac_signature="0" * 64, signed_at=NOW)
    res, _ = submit(req(approver_id=11), p, [forged])
    assert res.status is ApprovalStatus.PENDING_APPROVAL and res.approvals_received == 1


# ---- signatures -------------------------------------------------------------------------

def test_signature_depends_on_every_field():
    base = sign_approval(KEY, pay(), 10, True, NOW)
    assert base == sign_approval(KEY, pay(), 10, True, NOW)
    for changed in (pay(amount=Decimal("501")), pay(vendor_id=4), pay(invoice_id=9), pay(currency="USD"),
                    pay(company_id=2), pay(id=2)):
        assert sign_approval(KEY, changed, 10, True, NOW) != base
    assert sign_approval(KEY, pay(), 11, True, NOW) != base
    assert sign_approval(KEY, pay(), 10, False, NOW) != base
    assert sign_approval(KEY, pay(), 10, True, NOW + timedelta(seconds=1)) != base
    assert sign_approval(b"x" * 32, pay(), 10, True, NOW) != base


def test_amount_formatting_does_not_change_signature():
    assert sign_approval(KEY, pay(amount=Decimal("25000.50")), 10, True, NOW) == \
        sign_approval(KEY, pay(amount=Decimal("25000.5")), 10, True, NOW)


def test_short_key_refused():
    with pytest.raises(ApprovalKeyError):
        sign_approval(b"short", pay(), 10, True, NOW)


def test_load_key_from_env(monkeypatch):
    monkeypatch.delenv("APPROVAL_HMAC_KEY", raising=False)
    with pytest.raises(ApprovalKeyError):
        load_hmac_key()
    monkeypatch.setenv("APPROVAL_HMAC_KEY", "short")
    with pytest.raises(ApprovalKeyError):
        load_hmac_key()
    monkeypatch.setenv("APPROVAL_HMAC_KEY", "k" * 40)
    assert load_hmac_key() == b"k" * 40


# ---- execute_check ----------------------------------------------------------------------

def test_execute_allowed_with_one_valid_approval():
    p = pay()
    assert check(p, [approved_by(p, 10)]).allowed is True


def test_execute_denied_without_approvals():
    r = check(pay(), [])
    assert r.allowed is False and "0 valid" in r.reasons[0]


def test_execute_denied_when_big_amount_has_one_approval():
    p = pay(amount=Decimal("25000"))
    assert check(p, [approved_by(p, 10)]).allowed is False


def test_execute_allowed_with_two_approvals_big_amount():
    p = pay(amount=Decimal("25000"))
    assert check(p, [approved_by(p, 10), approved_by(p, 11)]).allowed is True


def test_execute_denied_if_amount_changed_after_approval():
    original = pay()
    records = [approved_by(original, 10)]
    changed = pay(amount=Decimal("499"))      # tampered after approval (Scenario: tampered payment)
    r = check(changed, records)
    assert r.allowed is False and any("tampering" in x for x in r.reasons)


def test_execute_denied_if_vendor_changed_after_approval():
    original = pay()
    r = check(pay(vendor_id=99), [approved_by(original, 10)])
    assert r.allowed is False


def test_execute_denied_for_expired_approval():
    p = pay()
    r = check(p, [approved_by(p, 10, at=NOW - timedelta(hours=73))])
    assert r.allowed is False and "0 valid" in r.reasons[-1]


def test_execute_denied_if_any_rejection():
    p = pay()
    r = check(p, [approved_by(p, 10), approved_by(p, 11, approve=False)])
    assert r.allowed is False and any("rejected" in x for x in r.reasons)


def test_execute_denied_if_creator_is_an_approver():
    p = pay()
    r = check(p, [approved_by(p, 7)])         # a forged-but-valid approval by the creator
    assert r.allowed is False and any("maker-checker" in x for x in r.reasons)


def test_execute_denied_if_already_paid():
    p = pay(status=InvoiceStatus.PAID_SIMULATED)
    assert check(p, [approved_by(p, 10)]).allowed is False


def test_execute_denied_for_wrong_company_or_payment():
    p = pay()
    assert check(p, [approved_by(p, 10)], company=2).allowed is False
    other = execute_check(ExecuteCheckRequest(payment_request_id=5, requested_by=7, company_id=1), p,
                          [approved_by(p, 10)], POLICY, KEY, NOW)
    assert other.allowed is False


def test_duplicate_approver_records_count_once():
    p = pay(amount=Decimal("25000"))
    assert check(p, [approved_by(p, 10), approved_by(p, 10)]).allowed is False
