from decimal import Decimal

import pytest
from app.gateway import LocalGateway
from app.main import app as default_app
from app.main import create_app
from app.store import (
    EGPACK,
    INV_0412,
    KARIM,
    MONA,
    OMAR,
    OUTSIDER,
    PR_187,
    PR_188,
    PR_190,
    SARA,
    VIEWER,
    seeded_store,
)
from fastapi.testclient import TestClient
from securefin_contracts import BankAccountStatus, Money


@pytest.fixture
def gateway():
    return LocalGateway(b"test-key")


@pytest.fixture
def store():
    return seeded_store()


@pytest.fixture
def client(store, gateway):
    return TestClient(create_app(store=store, gateway=gateway))


def as_user(user_id):
    return {"X-User-Id": str(user_id)}


def approve(client, request_id, user_id, approved=True):
    return client.post(f"/payment-requests/{request_id}/approvals", json={"approved": approved}, headers=as_user(user_id))


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
    assert body["pending"][0]["request"]["money"]["amount"] == "15400.00"


class TestCompanyIsolation:
    def test_other_company_sees_nothing(self, client):
        headers = as_user(OUTSIDER)
        assert client.get(f"/payment-requests/{PR_187}", headers=headers).status_code == 404
        assert client.get(f"/invoices/{INV_0412}", headers=headers).status_code == 404
        assert client.get(f"/vendors/{EGPACK}/bank-change", headers=headers).status_code == 404
        assert client.get("/dashboard", headers=headers).json()["pending_count"] == 0

    def test_other_company_cannot_approve(self, client):
        assert approve(client, PR_187, OUTSIDER).status_code == 404


class TestApprovals:
    def test_large_high_risk_request_is_held_for_two_approvals(self, client):
        gw = client.get(f"/payment-requests/{PR_187}", headers=as_user(KARIM)).json()["gateway"]
        assert gw["decision"] == "PENDING_APPROVAL"
        assert gw["required_approvers"] == 2
        assert gw["risk_score"] == 72
        assert set(gw["reasons"]) == {"ABOVE_DUAL_APPROVAL_LIMIT", "HIGH_RISK"}

    def test_creator_cannot_approve_own_request(self, client):
        res = approve(client, PR_190, KARIM)
        assert res.status_code == 403 and res.json()["detail"] == "SELF_APPROVAL"

    @pytest.mark.parametrize("user", [SARA, VIEWER])
    def test_roles_without_approval_rights_are_refused(self, client, user):
        assert approve(client, PR_187, user).status_code == 403

    def test_two_approvals_allow_and_approve(self, client):
        first = approve(client, PR_187, MONA)
        assert first.status_code == 201
        assert first.json()["gateway"]["decision"] == "PENDING_APPROVAL"

        second = approve(client, PR_187, KARIM).json()
        assert second["gateway"]["decision"] == "ALLOW"
        assert second["request"]["status"] == "approved"
        assert [a["approver"]["full_name"] for a in second["approvals"]] == ["Mona", "Karim Ashraf"]

    def test_same_approver_cannot_approve_twice(self, client):
        approve(client, PR_187, MONA)
        res = approve(client, PR_187, MONA)
        assert res.status_code == 409 and res.json()["detail"] == "ALREADY_DECIDED"

    def test_one_rejection_blocks(self, client):
        body = approve(client, PR_187, MONA, approved=False).json()
        assert body["gateway"]["decision"] == "BLOCK"
        assert body["request"]["status"] == "rejected"
        assert approve(client, PR_187, KARIM).status_code == 409

    def test_cannot_approve_payment_to_unverified_account(self, client, store):
        account_id = store.payment_requests[PR_188].bank_account_id
        store.bank_accounts[account_id] = store.bank_accounts[account_id].model_copy(update={"status": BankAccountStatus.ON_HOLD})
        res = approve(client, PR_188, MONA)
        assert res.status_code == 409 and "not verified" in res.json()["detail"]


class TestSignature:
    def test_signature_covers_amount_and_account(self, client, gateway, store):
        approve(client, PR_187, MONA)
        record = gateway.approvals(PR_187)[0]
        request = store.payment_requests[PR_187]
        iban = store.bank_accounts[request.bank_account_id].iban
        assert gateway.verify(record, request.money, iban)

        assert not gateway.verify(record, Money(amount=Decimal("99999.00")), iban)
        assert not gateway.verify(record, request.money, "EG450019000500000000099112233")


class BrokenGateway(LocalGateway):
    def decide(self, request, risk):
        raise TimeoutError("gateway too slow")

    def record(self, request, account, approver, approved):
        raise ConnectionError("gateway down")


class TestFailClosed:
    @pytest.fixture
    def gateway(self):
        return BrokenGateway(b"test-key")

    def test_gateway_down_means_block(self, client):
        gw = client.get(f"/payment-requests/{PR_187}", headers=as_user(KARIM)).json()["gateway"]
        assert gw["decision"] == "BLOCK"
        assert gw["reasons"] == ["GATEWAY_UNAVAILABLE"]

    def test_approval_fails_when_gateway_down(self, client, store):
        assert approve(client, PR_187, MONA).status_code == 503
        assert store.payment_requests[PR_187].status == "pending_approval"


def test_bank_change_view(client):
    body = client.get(f"/vendors/{EGPACK}/bank-change", headers=as_user(KARIM)).json()
    assert body["current"]["status"] == "verified"
    assert body["proposed"]["status"] == "on_hold"
    assert body["proposed"]["times_paid"] == 0
    assert body["requested_by"]["id"] == OMAR
