"""Audit behaviour added with the hardening PR: authorize decisions are logged; refusals go to the real tenant."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import app.main as main
import pytest
from app.stores import InMemoryApprovalStore
from fastapi.testclient import TestClient
from securefin_contracts import InvoiceStatus, PaymentRequestInfo

client = TestClient(main.app)


def auth_body(role="accountant", tool="create_payment_request", params=None, request_id="r1", company_id=1):
    params = {"invoice_id": 1, "vendor_id": 3, "amount": "500"} if params is None else params
    return {"user_id": 7, "role": role, "company_id": company_id, "request_id": request_id,
            "action": {"tool": tool, "params": params}}


# ---- every authorize decision is audited --------------------------------------------------

def test_every_decision_kind_is_audited_and_chain_holds():
    client.post("/v1/authorize", json=auth_body(role="viewer", request_id="a"))                       # BLOCK (role)
    client.post("/v1/authorize", json=auth_body(params={"amount": "-5"}, request_id="b"))             # BLOCK (params)
    client.post("/v1/authorize", json=auth_body(request_id="c"))                                      # PENDING
    client.post("/v1/authorize", json=auth_body(role="viewer", tool="get_invoices", params={}, request_id="d"))  # ALLOW
    entries = main.AUDIT_LOG.entries(1)
    assert [e.decision for e in entries] == ["BLOCK", "BLOCK", "PENDING_APPROVAL", "ALLOW"]
    assert all(e.action == "authorize" and e.source_service == "gateway" and e.user_id == 7 for e in entries)
    assert main.AUDIT_LOG.verify(1) is None


def test_response_carries_the_audit_entry_id():
    r = client.post("/v1/authorize", json=auth_body()).json()
    assert r["audit_entry_id"] == main.AUDIT_LOG.entries(1)[0].id


def test_payment_parameters_are_recorded():
    client.post("/v1/authorize", json=auth_body(params={"invoice_id": 4, "vendor_id": 9, "amount": "25000"}))
    p = main.AUDIT_LOG.entries(1)[0].parameters
    assert p["amount"] == "25000" and p["invoice_id"] == 4 and p["vendor_id"] == 9 and p["currency"] == "EGP"


def test_free_text_parameters_are_never_copied_into_the_log():
    secret = "EG380019000500000000263180002 and a private note"
    client.post("/v1/authorize", json=auth_body(role="admin", tool="search_policies", params={"query": secret}))
    entry = main.AUDIT_LOG.entries(1)[0]
    assert secret not in entry.model_dump_json() and "query" not in entry.parameters


def test_each_company_gets_its_own_chain():
    client.post("/v1/authorize", json=auth_body(company_id=1, request_id="x"))
    client.post("/v1/authorize", json=auth_body(company_id=2, request_id="x"))
    assert len(main.AUDIT_LOG.entries(1)) == 1 and len(main.AUDIT_LOG.entries(2)) == 1


def test_replayed_request_is_not_audited_twice():
    client.post("/v1/authorize", json=auth_body())
    client.post("/v1/authorize", json=auth_body())
    assert len(main.AUDIT_LOG.entries(1)) == 1


def test_audit_write_failure_blocks_the_action(monkeypatch):
    class BrokenLog:
        def append(self, event):
            raise RuntimeError("database down")

    monkeypatch.setattr(main, "AUDIT_LOG", BrokenLog())
    r = client.post("/v1/authorize", json=auth_body(role="viewer", tool="get_invoices", params={})).json()
    assert r["decision"] == "BLOCK" and "gateway error" in r["reasons"][0]   # a decision nobody can see is not allowed


def test_failed_audit_is_not_cached_so_a_retry_can_succeed(monkeypatch):
    class BrokenLog:
        def append(self, event):
            raise RuntimeError("database down")

    good = main.AUDIT_LOG
    monkeypatch.setattr(main, "AUDIT_LOG", BrokenLog())
    assert client.post("/v1/authorize", json=auth_body()).json()["decision"] == "BLOCK"
    monkeypatch.setattr(main, "AUDIT_LOG", good)
    assert client.post("/v1/authorize", json=auth_body()).json()["decision"] == "PENDING_APPROVAL"


# ---- approvals / execute-check are audited in the payment's real company -------------------

def payment(**kw):
    base = {"id": 1, "company_id": 1, "creator_id": 7, "invoice_id": 2, "vendor_id": 3, "amount": Decimal("500"),
            "currency": "EGP", "status": InvoiceStatus.PENDING_APPROVAL,
            "created_at": datetime.now(UTC) - timedelta(hours=1)}
    return PaymentRequestInfo(**{**base, **kw})


class FakePayments:
    def get(self, payment_request_id):
        return payment()


@pytest.fixture
def approvals_setup(monkeypatch):
    monkeypatch.setenv("APPROVAL_HMAC_KEY", "k" * 40)
    monkeypatch.setattr(main, "APPROVAL_STORE", InMemoryApprovalStore())
    monkeypatch.setattr(main, "PAYMENTS_CLIENT", FakePayments())


def approve(company_id, approver_id=10, role="approver"):
    body = {"payment_request_id": 1, "approver_id": approver_id, "approve": True, "approver_role": role}
    if company_id is not None:
        body["company_id"] = company_id
    return client.post("/v1/approvals/1", json=body)


def test_forged_company_cannot_write_into_another_tenants_log(approvals_setup):
    r = approve(company_id=2)                              # approver claims company 2; the payment is company 1's
    assert r.status_code == 403
    assert main.AUDIT_LOG.entries(2) == []                 # the claimed company's log stays clean
    entry = main.AUDIT_LOG.entries(1)[0]                   # the attempt shows up where the payment lives
    assert entry.decision == "BLOCK" and entry.parameters["claimed_company_id"] == 2


def test_missing_company_refusal_is_still_audited(approvals_setup):
    assert approve(company_id=None).status_code == 403
    entry = main.AUDIT_LOG.entries(1)[0]
    assert entry.decision == "BLOCK" and "claimed_company_id" not in entry.parameters


def test_execute_check_with_forged_company_is_audited_in_the_real_company(approvals_setup):
    r = client.post("/v1/execute-check", json={"payment_request_id": 1, "requested_by": 7, "company_id": 2})
    assert r.json()["allowed"] is False
    assert main.AUDIT_LOG.entries(2) == [] and main.AUDIT_LOG.entries(1)[0].parameters["claimed_company_id"] == 2


def test_unexpected_error_during_approval_is_503_and_audited(approvals_setup, monkeypatch):
    class Boom:
        def list(self, pid, company_id=None):
            raise RuntimeError("database down")

    monkeypatch.setattr(main, "APPROVAL_STORE", Boom())
    r = approve(company_id=1)
    assert r.status_code == 503
    assert main.AUDIT_LOG.entries(1)[0].result.startswith("503")


def test_audit_failure_on_execute_check_means_not_allowed(approvals_setup, monkeypatch):
    approve(company_id=1)                                  # approved
    ok = client.post("/v1/execute-check", json={"payment_request_id": 1, "requested_by": 7, "company_id": 1})
    assert ok.json()["allowed"] is True

    class BrokenLog:
        def append(self, event):
            raise RuntimeError("database down")

    monkeypatch.setattr(main, "AUDIT_LOG", BrokenLog())
    r = client.post("/v1/execute-check", json={"payment_request_id": 1, "requested_by": 7, "company_id": 1})
    assert r.json()["allowed"] is False                    # cannot be logged, so it must not be allowed


def test_refusal_still_reaches_the_caller_when_the_audit_log_is_down(approvals_setup, monkeypatch):
    class BrokenLog:
        def append(self, event):
            raise RuntimeError("database down")

    monkeypatch.setattr(main, "AUDIT_LOG", BrokenLog())
    assert approve(company_id=1, approver_id=7).status_code == 403    # maker-checker answer is not hidden
