import pytest
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def score(**features):
    resp = client.post("/v1/score", json={"invoice_id": 1, "features": features})
    assert resp.status_code == 200
    return resp.json()


def test_no_features_is_low_with_no_hits():
    r = score()
    assert r == {"score": 0.0, "level": "low", "rule_hits": [], "shap_reasons": [], "model_version": "rules-demo-v1"}


@pytest.mark.parametrize(("feature", "code", "points"), [
    ("duplicate_detected", "DUPLICATE_INVOICE", 70),
    ("bank_account_mismatch", "VENDOR_ACCOUNT_MISMATCH", 70),
    ("vendor_change_pending", "VENDOR_BANK_CHANGE_PENDING", 50),
    ("invoice_total_mismatch", "INVOICE_TOTAL_MISMATCH", 40),
])
def test_each_flag_adds_its_points(feature, code, points):
    r = score(**{feature: True})
    assert r["score"] == points and r["rule_hits"] == [code]


@pytest.mark.parametrize("value", ["true", 1, "yes", None])
def test_flags_need_a_real_boolean(value):
    assert score(duplicate_detected=value)["rule_hits"] == []


def test_score_is_capped_at_100():
    r = score(duplicate_detected=True, bank_account_mismatch=True, vendor_change_pending=True)
    assert r["score"] == 100 and r["level"] == "high" and len(r["rule_hits"]) == 3


@pytest.mark.parametrize(("amount", "hit"), [(99_999.99, False), (100_000, True), (250_000.5, True)])
def test_high_value_boundary(amount, hit):
    assert ("HIGH_VALUE_REVIEW" in score(invoice_total_egp=amount)["rule_hits"]) is hit


@pytest.mark.parametrize(("conf", "hit"), [(0.64, True), (0.65, False), (0.99, False)])
def test_low_ocr_confidence_boundary(conf, hit):
    assert ("LOW_OCR_CONFIDENCE" in score(ocr_confidence=conf)["rule_hits"]) is hit


@pytest.mark.parametrize("bad", [True, "100000", None])
def test_non_numeric_amount_and_confidence_are_ignored(bad):
    assert score(invoice_total_egp=bad, ocr_confidence=bad)["rule_hits"] == []


@pytest.mark.parametrize(("features", "level"), [
    ({"ocr_confidence": 0.1}, "low"),                                        # 15
    ({"invoice_total_mismatch": True}, "medium"),                            # 40
    ({"vendor_change_pending": True, "ocr_confidence": 0.1}, "medium"),      # 65
    ({"duplicate_detected": True}, "high"),                                  # 70 = gateway hold_score
])
def test_levels_follow_thresholds(features, level):
    assert score(**features)["level"] == level


def test_response_never_echoes_feature_values():
    body = client.post("/v1/score", json={"features": {"iban": "EG380019000500000000263180002",
                                                        "duplicate_detected": True}}).text
    assert "EG38" not in body
