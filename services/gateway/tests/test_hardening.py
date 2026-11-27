import app.main as main
import pytest
from app.idempotency import IdempotencyCache, RequestIdConflictError, fingerprint
from fastapi.testclient import TestClient
from securefin_contracts import AuthorizeRequest, Decision, GatewayDecision

client = TestClient(main.app)


def body(request_id="r1", amount="500", user_id=7, company_id=1, role="accountant"):
    return {"user_id": user_id, "role": role, "company_id": company_id, "request_id": request_id,
            "action": {"tool": "create_payment_request",
                       "params": {"invoice_id": 1, "vendor_id": 1, "amount": amount}}}


# ---- fail closed on crash -------------------------------------------------------------

class Crash:
    def score(self, invoice_id):
        raise RuntimeError("bug in the risk client")


def test_unexpected_error_in_authorize_blocks(monkeypatch):
    monkeypatch.setattr(main, "RISK_CLIENT", Crash())
    r = client.post("/v1/authorize", json=body())
    assert r.status_code == 200 and r.json()["decision"] == "BLOCK"
    assert "gateway error" in r.json()["reasons"][0]


def test_crash_decision_is_not_cached(monkeypatch):
    monkeypatch.setattr(main, "RISK_CLIENT", Crash())
    assert client.post("/v1/authorize", json=body()).json()["decision"] == "BLOCK"
    from conftest import FakeRisk
    monkeypatch.setattr(main, "RISK_CLIENT", FakeRisk(10))     # the bug is fixed; a retry must work
    assert client.post("/v1/authorize", json=body()).json()["decision"] == "PENDING_APPROVAL"


def test_unexpected_error_in_execute_check_is_not_allowed(monkeypatch):
    class Boom:
        def list(self, pid):
            raise RuntimeError("store exploded")

    monkeypatch.setenv("APPROVAL_HMAC_KEY", "k" * 40)
    monkeypatch.setattr(main, "APPROVAL_STORE", Boom())

    class P:
        def get(self, pid):
            from datetime import UTC, datetime
            from decimal import Decimal

            from securefin_contracts import InvoiceStatus, PaymentRequestInfo
            return PaymentRequestInfo(id=1, company_id=1, creator_id=7, invoice_id=2, vendor_id=3,
                                      amount=Decimal("5"), currency="EGP", status=InvoiceStatus.PENDING_APPROVAL,
                                      created_at=datetime.now(UTC))

    monkeypatch.setattr(main, "PAYMENTS_CLIENT", P())
    r = client.post("/v1/execute-check", json={"payment_request_id": 1, "requested_by": 7, "company_id": 1})
    assert r.status_code == 200 and r.json()["allowed"] is False


# ---- replay protection ----------------------------------------------------------------

def test_same_request_twice_returns_same_decision(monkeypatch):
    calls = []

    class Counting:
        def score(self, invoice_id):
            from securefin_contracts import RiskLevel, RiskScore
            calls.append(invoice_id)
            return RiskScore(score=10, level=RiskLevel.LOW)

    monkeypatch.setattr(main, "RISK_CLIENT", Counting())
    first = client.post("/v1/authorize", json=body()).json()
    second = client.post("/v1/authorize", json=body()).json()
    assert first == second and len(calls) == 1                  # the second answer came from the cache


def test_same_request_id_other_payload_is_conflict():
    assert client.post("/v1/authorize", json=body(amount="500")).status_code == 200
    r = client.post("/v1/authorize", json=body(amount="25000"))
    assert r.status_code == 409


def test_same_request_id_other_role_is_conflict():
    assert client.post("/v1/authorize", json=body(role="accountant")).status_code == 200
    assert client.post("/v1/authorize", json=body(role="admin")).status_code == 409


def test_request_id_is_scoped_per_user_and_company():
    assert client.post("/v1/authorize", json=body(user_id=7)).status_code == 200
    assert client.post("/v1/authorize", json=body(user_id=8, amount="25000")).status_code == 200
    assert client.post("/v1/authorize", json=body(company_id=2, amount="25000")).status_code == 200


def test_block_decisions_are_cached_too():
    first = client.post("/v1/authorize", json=body(amount="-5")).json()
    assert first["decision"] == "BLOCK"
    assert client.post("/v1/authorize", json=body(amount="-5")).json() == first


# ---- cache unit tests -----------------------------------------------------------------

def req(request_id="a", amount="1"):
    return AuthorizeRequest.model_validate(body(request_id=request_id, amount=amount))


def test_cache_expires_after_ttl():
    now = [0.0]
    c = IdempotencyCache(ttl_seconds=10, clock=lambda: now[0])
    c.put(req(), GatewayDecision(decision=Decision.ALLOW))
    assert c.get(req()) is not None
    now[0] = 11
    assert c.get(req()) is None
    assert c.get(req(amount="999")) is None                    # expired entry no longer conflicts


def test_cache_is_bounded():
    c = IdempotencyCache(max_items=3)
    for i in range(5):
        c.put(req(request_id=f"id{i}"), GatewayDecision(decision=Decision.ALLOW))
    assert c.get(req(request_id="id0")) is None and c.get(req(request_id="id4")) is not None


def test_cache_conflict_raises():
    c = IdempotencyCache()
    c.put(req(amount="1"), GatewayDecision(decision=Decision.ALLOW))
    with pytest.raises(RequestIdConflictError):
        c.get(req(amount="2"))


def test_fingerprint_is_stable_and_sensitive():
    assert fingerprint(req()) == fingerprint(req())
    assert fingerprint(req(amount="1")) != fingerprint(req(amount="2"))
