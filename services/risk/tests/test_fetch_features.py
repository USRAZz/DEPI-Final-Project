from decimal import Decimal

import app.main as main
import httpx
import pytest
from app.features_client import FeaturesClient, FeaturesUnavailableError
from fastapi.testclient import TestClient
from securefin_contracts import RiskFeatures

client = TestClient(main.app)


class FakeFeatures:
    def __init__(self, features: RiskFeatures | None = None, fail: bool = False):
        self.features, self.fail, self.calls = features or RiskFeatures(), fail, []

    def fetch(self, invoice_id: int) -> RiskFeatures:
        self.calls.append(invoice_id)
        if self.fail:
            raise FeaturesUnavailableError("down")
        return self.features


@pytest.fixture
def fake(monkeypatch):
    def install(**kw):
        f = FakeFeatures(**kw)
        monkeypatch.setattr(main, "FEATURES_CLIENT", f)
        return f
    return install


# ---- scoring endpoint ------------------------------------------------------------------

def test_invoice_id_only_fetches_features_from_api(fake):
    f = fake(features=RiskFeatures(duplicate_detected=True))
    r = client.post("/v1/score", json={"invoice_id": 5}).json()
    assert f.calls == [5] and r["score"] == 70 and r["rule_hits"] == ["DUPLICATE_INVOICE"]


def test_all_fetched_features_are_scored(fake):
    fake(features=RiskFeatures(vendor_change_pending=True, invoice_total_egp=Decimal("150000.00"), ocr_confidence=0.5))
    r = client.post("/v1/score", json={"invoice_id": 1}).json()
    assert r["rule_hits"] == ["VENDOR_BANK_CHANGE_PENDING", "HIGH_VALUE_REVIEW", "LOW_OCR_CONFIDENCE"]
    assert r["score"] == 85 and r["level"] == "high"


def test_unknown_features_score_zero(fake):
    fake(features=RiskFeatures())
    assert client.post("/v1/score", json={"invoice_id": 1}).json()["score"] == 0


def test_api_unavailable_returns_503_never_a_low_score(fake):
    fake(fail=True)
    resp = client.post("/v1/score", json={"invoice_id": 1})
    assert resp.status_code == 503 and "unavailable" in resp.json()["detail"]


def test_explicit_features_skip_the_api(fake):
    f = fake(fail=True)
    r = client.post("/v1/score", json={"invoice_id": 1, "features": {"bank_account_mismatch": True}}).json()
    assert f.calls == [] and r["rule_hits"] == ["VENDOR_ACCOUNT_MISMATCH"]


def test_no_invoice_id_and_no_features_does_not_call_api(fake):
    f = fake(fail=True)
    assert client.post("/v1/score", json={}).json()["score"] == 0 and f.calls == []


# ---- http client -----------------------------------------------------------------------

def _fc(handler, token="secret"):
    return FeaturesClient("http://api", token, 1, transport=httpx.MockTransport(handler))


def test_client_sends_token_and_parses_features():
    seen = {}

    def handler(req):
        seen["url"], seen["token"] = str(req.url), req.headers.get("X-Service-Token")
        return httpx.Response(200, json={"duplicate_detected": True, "invoice_total_egp": "1200.50"})

    feats = _fc(handler).fetch(7)
    assert seen == {"url": "http://api/v1/invoices/7/risk-features", "token": "secret"}
    assert feats.duplicate_detected is True and feats.invoice_total_egp == Decimal("1200.50")


def test_client_without_token_refuses_to_call():
    called = []
    with pytest.raises(FeaturesUnavailableError):
        _fc(lambda req: called.append(1) or httpx.Response(200, json={}), token="").fetch(1)
    assert called == []


@pytest.mark.parametrize("handler", [
    lambda req: httpx.Response(401),                                   # wrong token
    lambda req: httpx.Response(404),                                   # unknown invoice / endpoint not built yet
    lambda req: httpx.Response(500),
    lambda req: httpx.Response(200, text="not json"),
    lambda req: httpx.Response(200, json={"ocr_confidence": 7}),       # out of 0-1
    lambda req: httpx.Response(200, json={"iban": "EG38..."}),         # raw bank data is not a feature
    lambda req: (_ for _ in ()).throw(httpx.ConnectTimeout("slow")),
])
def test_client_failures_become_unavailable(handler):
    with pytest.raises(FeaturesUnavailableError):
        _fc(handler).fetch(1)
