from datetime import UTC, datetime, timedelta

import pytest
from app.main import app as default_app
from app.main import create_app
from app.store import (
    ACC_NILE,
    EGPACK,
    INV_0412,
    KARIM,
    MONA,
    OMAR,
    OUTSIDER,
    PR_187,
    PR_188,
    PR_189,
    PR_190,
    SARA,
    VIEWER,
    seeded_store,
)
from fastapi.testclient import TestClient
from securefin_contracts import ApprovalRequest, ApprovalResult, BankAccountStatus, ExecuteCheckRequest
from tests.fakes import DownGateway, FakeGateway


@pytest.fixture
def store():
    return seeded_store()


@pytest.fixture
def gateway(store):
    return FakeGateway(store)


@pytest.fixture
def client(store, gateway):
    return TestClient(create_app(store=store, gateway=gateway))


def as_user(user_id):
    return {"X-User-Id": str(user_id)}


def approve(client, request_id, user_id, approved=True, **extra):
    body = {"approved": approved, **extra}
    return client.post(f"/payment-requests/{request_id}/approvals", json=body, headers=as_user(user_id))


def execute(client, request_id, user_id):
    return client.post(f"/payment-requests/{request_id}/execute", headers=as_user(user_id))


def test_health():
    assert TestClient(default_app).get("/health").json() == {"service": "api", "status": "ok"}


def test_requires_sign_in(client):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers=as_user(9999)).status_code == 401


def test_me(client):
    body = client.get("/me", headers=as_user(KARIM)).json()
    assert body["full_name"] == "Karim Ashraf" and body["role"] == "admin"


def test_dashboard_counts_and_money_as_string(client):
    body = client.get("/dashboard", headers=as_user(KARIM)).json()
    assert body["pending_count"] == 4
    assert body["above_limit_count"] == 2
    assert body["flagged_count"] == 1
    assert body["on_hold_count"] == 1
    assert body["month_spend"] == {"amount": "486250.00", "currency": "EGP"}
    assert body["pending"][0]["request"]["amount"] == "15400.00"


class TestCompanyIsolation:
    def test_other_company_sees_nothing(self, client):
        headers = as_user(OUTSIDER)
        assert client.get(f"/payment-requests/{PR_187}", headers=headers).status_code == 404
        assert client.get(f"/invoices/{INV_0412}", headers=headers).status_code == 404
        assert client.get(f"/vendors/{EGPACK}/bank-change", headers=headers).status_code == 404
        assert client.get("/dashboard", headers=headers).json()["pending_count"] == 0

    def test_other_company_cannot_approve_or_execute(self, client, gateway):
        assert approve(client, PR_187, OUTSIDER).status_code == 404
        assert execute(client, PR_187, OUTSIDER).status_code == 404
        assert gateway.sent == []


class TestApprovals:
    def test_before_any_approval_two_are_expected_above_the_limit(self, client):
        approval = client.get(f"/payment-requests/{PR_187}", headers=as_user(KARIM)).json()["approval"]
        assert approval == {"status": "PENDING_APPROVAL", "approvals_received": 0, "approvals_required": 2, "reasons": []}

    def test_role_and_company_are_sent_from_the_session(self, client, gateway):
        approve(client, PR_187, MONA, comment="checked the invoice")
        assert gateway.sent == [ApprovalRequest(payment_request_id=PR_187, approver_id=MONA, approve=True,
                                                comment="checked the invoice", approver_role="approver", company_id=1)]

    def test_client_cannot_send_role_or_company(self, client, gateway):
        assert approve(client, PR_187, MONA, approver_role="admin").status_code == 422
        assert approve(client, PR_187, MONA, company_id=2).status_code == 422
        assert gateway.sent == []

    def test_creator_is_refused_with_the_gateways_reasons(self, client):
        res = approve(client, PR_190, KARIM)
        assert res.status_code == 403
        assert res.json()["detail"] == ["maker-checker: the creator cannot approve their own payment request"]

    @pytest.mark.parametrize("user", [SARA, VIEWER])
    def test_roles_without_approval_rights_never_reach_the_gateway(self, client, gateway, user):
        assert approve(client, PR_187, user).status_code == 403
        assert gateway.sent == []

    def test_two_approvals_approve_but_wait_for_execution(self, client):
        first = approve(client, PR_187, MONA)
        assert first.status_code == 201
        assert first.json()["approval"]["status"] == "PENDING_APPROVAL"

        second = approve(client, PR_187, KARIM).json()
        assert second["approval"] == {"status": "APPROVED", "approvals_received": 2, "approvals_required": 2, "reasons": []}
        # Stays PENDING_APPROVAL: execute-check only allows a payment in that status.
        assert second["request"]["status"] == "PENDING_APPROVAL"
        assert [a["approver"]["full_name"] for a in second["approvals"]] == ["Mona", "Karim Ashraf"]

    def test_same_approver_cannot_approve_twice(self, client):
        approve(client, PR_187, MONA)
        res = approve(client, PR_187, MONA)
        assert res.status_code == 403
        assert res.json()["detail"] == ["this approver has already decided on this payment request"]

    def test_one_rejection_rejects_the_request(self, client):
        body = approve(client, PR_187, MONA, approved=False).json()
        assert body["approval"]["status"] == "REJECTED"
        assert body["request"]["status"] == "REJECTED"
        assert approve(client, PR_187, KARIM).status_code == 409

    def test_expired_answer_is_shown_but_not_listed_as_an_approval(self, client, gateway):
        def expired(req):
            gateway.sent.append(req)
            return ApprovalResult(payment_request_id=req.payment_request_id, status="EXPIRED", approvals_received=0,
                                  approvals_required=1, reasons=["approval window has expired"])

        gateway.submit_approval = expired
        body = approve(client, PR_189, MONA).json()
        assert body["approval"]["status"] == "EXPIRED"
        assert body["approval"]["reasons"] == ["approval window has expired"]
        assert body["approvals"] == []

    def test_cannot_approve_payment_to_unverified_account(self, client, store, gateway):
        account_id = store.payment_requests[PR_188].bank_account_id
        store.bank_accounts[account_id] = store.bank_accounts[account_id].model_copy(update={"status": BankAccountStatus.ON_HOLD})
        res = approve(client, PR_188, MONA)
        assert res.status_code == 409 and "not verified" in res.json()["detail"]
        assert gateway.sent == []


class TestExecution:
    def test_pays_only_after_execute_check_allows(self, client, gateway, store):
        approve(client, PR_187, MONA)
        approve(client, PR_187, KARIM)
        res = execute(client, PR_187, SARA)
        assert res.status_code == 200
        assert res.json()["executed"] is True
        assert res.json()["request"]["status"] == "PAID_SIMULATED"
        assert gateway.sent[-1] == ExecuteCheckRequest(payment_request_id=PR_187, requested_by=SARA, company_id=1)
        assert store.times_paid[ACC_NILE] == 10

    def test_not_enough_approvals_is_refused_and_nothing_is_paid(self, client, store):
        approve(client, PR_187, MONA)
        res = execute(client, PR_187, SARA)
        assert res.status_code == 409
        assert res.json()["detail"] == ["1 valid approval(s), 2 required"]
        assert store.payment_requests[PR_187].status == "PENDING_APPROVAL"

    def test_cannot_pay_twice(self, client):
        approve(client, PR_189, MONA)
        assert execute(client, PR_189, SARA).status_code == 200
        res = execute(client, PR_189, SARA)
        assert res.status_code == 409 and "PAID_SIMULATED" in res.json()["detail"][0]

    @pytest.mark.parametrize("user", [MONA, VIEWER])
    def test_roles_without_execute_rights_are_refused(self, client, user):
        approve(client, PR_189, MONA)
        assert execute(client, PR_189, user).status_code == 403

    def test_account_put_on_hold_after_approval_blocks_payment(self, client, store, gateway):
        approve(client, PR_189, MONA)
        account_id = store.payment_requests[PR_189].bank_account_id
        store.bank_accounts[account_id] = store.bank_accounts[account_id].model_copy(update={"status": BankAccountStatus.ON_HOLD})
        assert execute(client, PR_189, SARA).status_code == 409
        assert not any(isinstance(s, ExecuteCheckRequest) for s in gateway.sent)


class TestFailClosed:
    @pytest.fixture
    def gateway(self):
        return DownGateway()

    def test_approval_fails_when_gateway_down(self, client, store):
        res = approve(client, PR_187, MONA)
        assert res.status_code == 503 and res.json()["detail"] == ["gateway unavailable: nothing was approved"]
        assert store.payment_requests[PR_187].status == "PENDING_APPROVAL"
        assert store.approvals == {}

    def test_payment_fails_when_gateway_down(self, client, store):
        res = execute(client, PR_189, SARA)
        assert res.status_code == 503 and res.json()["detail"] == ["gateway unavailable: nothing was paid"]
        assert store.payment_requests[PR_189].status == "PENDING_APPROVAL"


def test_bank_change_view(client):
    body = client.get(f"/vendors/{EGPACK}/bank-change", headers=as_user(KARIM)).json()
    assert body["current"]["status"] == "verified"
    assert body["proposed"]["status"] == "on_hold"
    assert body["proposed"]["times_paid"] == 0
    assert body["requested_by"]["id"] == OMAR


class TestPaymentInfoForGateway:
    @pytest.fixture(autouse=True)
    def service_token(self, monkeypatch):
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "test-service-token")

    def test_returns_payment_request_info(self, client, store):
        res = client.get(f"/payments/{PR_187}", headers={"X-Service-Token": "test-service-token"})
        assert res.status_code == 200
        created_at = store.payment_requests[PR_187].created_at.isoformat().replace("+00:00", "Z")
        assert res.json() == {
            "id": PR_187, "company_id": 1, "creator_id": SARA, "invoice_id": INV_0412, "vendor_id": 1,
            "amount": "15400.00", "currency": "EGP", "status": "PENDING_APPROVAL", "created_at": created_at,
        }

    def test_sample_requests_are_inside_the_gateways_72_hour_window(self, store):
        now = datetime.now(UTC)
        assert all(now - p.created_at < timedelta(hours=72) for p in store.payment_requests.values())

    def test_unknown_payment_is_404(self, client):
        assert client.get("/payments/9999", headers={"X-Service-Token": "test-service-token"}).status_code == 404

    @pytest.mark.parametrize("headers", [{}, {"X-Service-Token": "wrong"}, as_user(KARIM)])
    def test_needs_the_service_token(self, client, headers):
        assert client.get(f"/payments/{PR_187}", headers=headers).status_code == 401
