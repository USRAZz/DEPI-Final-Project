from app.audit_chain import GENESIS, compute_hash, verify_chain
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _req(role, amount="500"):
    return {"user_id": 7, "role": role, "company_id": 1, "request_id": "t",
            "action": {"tool": "create_payment_request",
                       "params": {"invoice_id": 1, "vendor_id": 1, "amount": amount}}}


def test_viewer_cannot_create_payment():  # Scenario B / T-04
    r = client.post("/v1/authorize", json=_req("viewer")).json()
    assert r["decision"] == "BLOCK"


def test_negative_amount_blocked():  # T-12
    r = client.post("/v1/authorize", json=_req("accountant", "-5")).json()
    assert r["decision"] == "BLOCK"


def test_dual_approval_above_threshold():  # T-09
    r = client.post("/v1/authorize", json=_req("accountant", "25000")).json()
    assert r["decision"] == "PENDING_APPROVAL" and r["required_approvers"] == 2


def test_audit_tampering_detected():  # Scenario G / T-11
    e1 = {"action": "login", "user_id": 1}
    h1 = compute_hash(e1, GENESIS)
    e2 = {"action": "pay", "user_id": 1, "amount": 100}
    h2 = compute_hash(e2, h1)
    chain = [{**e1, "prev_hash": GENESIS, "entry_hash": h1}, {**e2, "prev_hash": h1, "entry_hash": h2}]
    assert verify_chain(chain) is None
    chain[1]["amount"] = 9999
    assert verify_chain(chain) == 1
