import app.main as main
import httpx
import pytest
from app.risk_client import RiskClient, RiskUnavailableError
from fastapi.testclient import TestClient
from securefin_contracts import RiskLevel, RiskScore

client = TestClient(main.app)


class Boom:
    def score(self, invoice_id):
        raise RiskUnavailableError("down")


class Fixed:
    def __init__(self, v):
        self.v = v

    def score(self, invoice_id):
        return RiskScore(score=self.v, level=RiskLevel.HIGH)


def _pay(amount="500"):
    return {"user_id": 7, "role": "accountant", "company_id": 1, "request_id": "t",
            "action": {"tool": "create_payment_request",
                       "params": {"invoice_id": 1, "vendor_id": 1, "amount": amount}}}


def test_low_risk_is_scored_and_recorded():
    r = client.post("/v1/authorize", json=_pay()).json()
    assert r["risk_score"] == 10 and "risk_check" in r["checks_passed"]
    assert r["decision"] == "PENDING_APPROVAL" and r["required_approvers"] == 1


@pytest.mark.parametrize(("score", "held"), [(69.9, False), (70, True), (95, True)])
def test_hold_score_boundary(monkeypatch, score, held):
    monkeypatch.setattr(main, "RISK_CLIENT", Fixed(score))
    r = client.post("/v1/authorize", json=_pay()).json()
    assert any("high risk" in x for x in r["reasons"]) is held
    assert r["decision"] == "PENDING_APPROVAL" and r["risk_score"] == score


def test_risk_unavailable_holds_never_allows(monkeypatch):
    monkeypatch.setattr(main, "RISK_CLIENT", Boom())
    r = client.post("/v1/authorize", json=_pay()).json()
    assert r["decision"] == "PENDING_APPROVAL" and r["risk_score"] is None
    assert any("unavailable" in x for x in r["reasons"]) and "risk_check" not in r["checks_passed"]


def test_risk_not_called_for_blocked_request(monkeypatch):
    monkeypatch.setattr(main, "RISK_CLIENT", Boom())
    body = _pay("-5")
    assert client.post("/v1/authorize", json=body).json()["decision"] == "BLOCK"


def test_high_risk_and_big_amount_keeps_both_reasons(monkeypatch):
    monkeypatch.setattr(main, "RISK_CLIENT", Fixed(90))
    r = client.post("/v1/authorize", json=_pay("25000")).json()
    assert r["required_approvers"] == 2 and len(r["reasons"]) == 2


def _rc(handler):
    return RiskClient("http://risk", 1, transport=httpx.MockTransport(handler))


def test_client_parses_valid_response():
    ok = _rc(lambda req: httpx.Response(200, json={"score": 42, "level": "medium"}))
    assert ok.score(1).score == 42


def test_client_sends_invoice_id():
    seen = {}

    def handler(req):
        seen["url"], seen["body"] = str(req.url), req.content
        return httpx.Response(200, json={"score": 1, "level": "low"})

    _rc(handler).score(5)
    assert seen["url"].endswith("/v1/score") and b'"invoice_id":5' in seen["body"]


@pytest.mark.parametrize("handler", [
    lambda req: httpx.Response(500),
    lambda req: httpx.Response(503, json={"score": 1, "level": "low"}),   # error status, valid-looking body
    lambda req: httpx.Response(200, text="not json"),
    lambda req: httpx.Response(200, json={"score": 500, "level": "low"}),   # out of 0-100
    lambda req: httpx.Response(200, json={"level": "low"}),
    lambda req: (_ for _ in ()).throw(httpx.ConnectTimeout("slow")),
])
def test_client_failures_become_unavailable(handler):
    with pytest.raises(RiskUnavailableError):
        _rc(handler).score(1)
