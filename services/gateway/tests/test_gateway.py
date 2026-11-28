import pytest
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app, headers={"X-Service-Token": "test-gateway-token"})  # see conftest.caller_token


def test_health():
    assert client.get("/health").json()["status"] == "ok"


# ---- caller token: only the api may ask the gateway for decisions -----------------------------------------

anonymous = TestClient(app)
PAY = {"user_id": 1, "role": "accountant", "company_id": 1, "request_id": "t",
       "action": {"tool": "create_payment_request", "params": {"invoice_id": 1, "vendor_id": 1, "amount": "10",
                                                               "currency": "EGP"}}}
DECISION_CALLS = [
    ("/v1/authorize", PAY),
    ("/v1/approvals/1", {"payment_request_id": 1, "approver_id": 10, "approve": True, "approver_role": "approver",
                         "company_id": 1}),
    ("/v1/execute-check", {"payment_request_id": 1, "requested_by": 7, "company_id": 1}),
]


@pytest.mark.parametrize(("path", "body"), DECISION_CALLS)
@pytest.mark.parametrize("headers", [{}, {"X-Service-Token": ""}, {"X-Service-Token": "wrong"}])
def test_decisions_need_the_caller_token(path, body, headers):
    assert anonymous.post(path, json=body, headers=headers).status_code == 401


@pytest.mark.parametrize(("path", "body"), DECISION_CALLS)
def test_decisions_are_closed_when_no_token_is_configured(path, body, monkeypatch):
    monkeypatch.delenv("GATEWAY_SERVICE_TOKEN")
    assert client.post(path, json=body).status_code == 503


def test_audit_token_is_not_the_caller_token(monkeypatch):
    monkeypatch.setenv("AUDIT_VERIFY_TOKEN", "audit-only-token")
    r = anonymous.post("/v1/authorize", json=PAY, headers={"X-Service-Token": "audit-only-token"})
    assert r.status_code == 401
