from datetime import UTC, datetime, timedelta
from decimal import Decimal

import app.main as main
import pytest
from app.payments_client import PaymentNotFoundError, PaymentsUnavailableError
from app.stores import InMemoryApprovalStore
from fastapi.testclient import TestClient
from securefin_contracts import InvoiceStatus, PaymentRequestInfo

client = TestClient(main.app)


def make_payment(**kw) -> PaymentRequestInfo:
    base = {"id": 1, "company_id": 1, "creator_id": 7, "invoice_id": 2, "vendor_id": 3, "amount": Decimal("500"),
            "currency": "EGP", "status": InvoiceStatus.PENDING_APPROVAL,
            "created_at": datetime.now(UTC) - timedelta(hours=1)}
    return PaymentRequestInfo(**{**base, **kw})


class FakePayments:
    def __init__(self, payment=None, error=None):
        self.payment, self.error = payment, error

    def get(self, payment_request_id):
        if self.error:
            raise self.error
        return self.payment


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setenv("APPROVAL_HMAC_KEY", "k" * 40)
    monkeypatch.setattr(main, "APPROVAL_STORE", InMemoryApprovalStore())
    monkeypatch.setattr(main, "PAYMENTS_CLIENT", FakePayments(make_payment()))


def use_payment(monkeypatch, **kw):
    monkeypatch.setattr(main, "PAYMENTS_CLIENT", FakePayments(make_payment(**kw)))


def approve(approver_id=10, role="approver", approve_=True, company_id=1, pid=1, path_id=None):
    body = {"payment_request_id": pid, "approver_id": approver_id, "approve": approve_,
            "approver_role": role, "company_id": company_id}
    return client.post(f"/v1/approvals/{path_id or pid}", json=body)


def execute(pid=1, company_id=1):
    return client.post("/v1/execute-check", json={"payment_request_id": pid, "requested_by": 7,
                                                  "company_id": company_id})


def test_full_flow_small_payment():
    assert execute().json()["allowed"] is False            # nothing approved yet
    r = approve()
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"
    assert execute().json()["allowed"] is True


def test_big_payment_needs_two(monkeypatch):
    use_payment(monkeypatch, amount=Decimal("25000"))
    assert approve(10).json()["status"] == "PENDING_APPROVAL"
    assert execute().json()["allowed"] is False
    assert approve(11).json()["status"] == "APPROVED"
    assert execute().json()["allowed"] is True


def test_creator_cannot_approve():
    r = approve(approver_id=7)
    assert r.status_code == 403 and "maker-checker" in r.json()["detail"][0]
    assert execute().json()["allowed"] is False


def test_second_decision_by_same_person_refused():
    assert approve().status_code == 200
    assert approve().status_code == 403


@pytest.mark.parametrize("role", ["viewer", "accountant"])
def test_wrong_role_refused(role):
    assert approve(role=role).status_code == 403


def test_other_company_refused():
    assert approve(company_id=2).status_code == 403


def test_missing_role_and_company_refused():
    r = client.post("/v1/approvals/1", json={"payment_request_id": 1, "approver_id": 10, "approve": True})
    assert r.status_code == 403


def test_path_and_body_must_match():
    assert approve(pid=1, path_id=2).status_code == 422


def test_reject_stops_execution():
    assert approve(10, approve_=False).json()["status"] == "REJECTED"
    assert execute().json()["allowed"] is False
    assert approve(11).status_code == 403                    # already rejected


def test_amount_changed_after_approval_blocks_execution(monkeypatch):
    assert approve().json()["status"] == "APPROVED"
    use_payment(monkeypatch, amount=Decimal("499"))           # api data changed after approval
    r = execute().json()
    assert r["allowed"] is False and any("tampering" in x for x in r["reasons"])


def test_payment_already_paid_cannot_execute_again(monkeypatch):
    assert approve().status_code == 200
    use_payment(monkeypatch, status=InvoiceStatus.PAID_SIMULATED)
    assert execute().json()["allowed"] is False


def test_expired_request(monkeypatch):
    use_payment(monkeypatch, created_at=datetime.now(UTC) - timedelta(hours=100))
    assert approve().json()["status"] == "EXPIRED"
    assert execute().json()["allowed"] is False


@pytest.mark.parametrize("call", [approve, execute])
def test_payment_service_down_fails_closed(monkeypatch, call):
    monkeypatch.setattr(main, "PAYMENTS_CLIENT", FakePayments(error=PaymentsUnavailableError("down")))
    assert call().status_code == 503


@pytest.mark.parametrize("call", [approve, execute])
def test_unknown_payment_is_404(monkeypatch, call):
    monkeypatch.setattr(main, "PAYMENTS_CLIENT", FakePayments(error=PaymentNotFoundError(1)))
    assert call().status_code == 404


@pytest.mark.parametrize("key", [None, "short"])
@pytest.mark.parametrize("call", [approve, execute])
def test_missing_or_short_key_fails_closed(monkeypatch, call, key):
    if key is None:
        monkeypatch.delenv("APPROVAL_HMAC_KEY")
    else:
        monkeypatch.setenv("APPROVAL_HMAC_KEY", key)
    assert call().status_code == 503
    assert main.APPROVAL_STORE.list(1) == []


def test_denied_approval_stores_nothing():
    approve(approver_id=7)
    assert main.APPROVAL_STORE.list(1) == []
