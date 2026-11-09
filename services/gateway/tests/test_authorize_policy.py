import pytest
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _pay(role="accountant", amount="500", currency=None):
    params = {"invoice_id": 1, "vendor_id": 1, "amount": amount}
    if currency:
        params["currency"] = currency
    return {"user_id": 7, "role": role, "company_id": 1, "request_id": "t",
            "action": {"tool": "create_payment_request", "params": params}}


def _read(role, tool):
    return {"user_id": 7, "role": role, "company_id": 1, "request_id": "t",
            "action": {"tool": tool, "params": {}}}


def test_threshold_boundary_needs_one_approver():
    r = client.post("/v1/authorize", json=_pay(amount="10000")).json()
    assert r["decision"] == "PENDING_APPROVAL" and r["required_approvers"] == 1


def test_just_above_threshold_needs_two():
    r = client.post("/v1/authorize", json=_pay(amount="10000.01")).json()
    assert r["decision"] == "PENDING_APPROVAL" and r["required_approvers"] == 2


def test_foreign_currency_needs_two_with_reason():
    r = client.post("/v1/authorize", json=_pay(amount="5", currency="USD")).json()
    assert r["required_approvers"] == 2
    assert "USD" in r["reasons"][0]


@pytest.mark.parametrize(("role", "tool", "decision"), [
    ("viewer", "get_invoices", "ALLOW"),
    ("viewer", "check_duplicate", "BLOCK"),
    ("approver", "create_payment_request", "BLOCK"),
    ("approver", "get_risk_score", "ALLOW"),
    ("accountant", "search_policies", "BLOCK"),
    ("admin", "search_policies", "ALLOW"),
])
def test_role_tool_matrix(role, tool, decision):
    assert client.post("/v1/authorize", json=_read(role, tool)).json()["decision"] == decision
