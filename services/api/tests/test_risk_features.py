from decimal import Decimal

import pytest
from app.main import create_app
from app.risk_features import compute_risk_features
from app.store import ACC_EGPACK_NEW, EGPACK, INV_0412, NILE, seeded_store
from fastapi.testclient import TestClient
from securefin_contracts import BankAccountStatus

TOKEN = "test-service-token"
URL = f"/v1/invoices/{INV_0412}/risk-features"


@pytest.fixture
def store():
    return seeded_store()


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    return TestClient(create_app(store=store))


def edit_invoice(store, **changes):
    store.invoices[INV_0412] = store.invoices[INV_0412].model_copy(update=changes)


def edit_fields(store, **changes):
    inv = store.invoices[INV_0412]
    edit_invoice(store, fields=inv.fields.model_copy(update=changes))


# ---- endpoint and service token --------------------------------------------------------

def test_endpoint_returns_features_with_token(client):
    r = client.get(URL, headers={"X-Service-Token": TOKEN})
    assert r.status_code == 200
    assert r.json() == {
        "duplicate_detected": True,          # sample invoice 412 duplicates 371
        "invoice_total_mismatch": False,
        "ocr_confidence": 0.72,              # lowest field confidence (iban)
        "invoice_total_egp": "15400.00",
        "bank_account_mismatch": False,      # invoice IBAN equals Nile Paper's verified account
        "vendor_change_pending": False,
    }


@pytest.mark.parametrize("headers", [{}, {"X-Service-Token": "wrong"}, {"X-User-Id": "1"}])
def test_endpoint_rejects_missing_or_wrong_token(client, headers):
    assert client.get(URL, headers=headers).status_code == 401


def test_endpoint_rejects_everyone_when_server_token_unset(store, monkeypatch):
    monkeypatch.delenv("INTERNAL_SERVICE_TOKEN", raising=False)
    c = TestClient(create_app(store=store))
    assert c.get(URL, headers={"X-Service-Token": ""}).status_code == 401


def test_unknown_invoice_is_404(client):
    assert client.get("/v1/invoices/999999/risk-features", headers={"X-Service-Token": TOKEN}).status_code == 404


def test_response_never_contains_an_iban(client):
    assert "EG38" not in client.get(URL, headers={"X-Service-Token": TOKEN}).text


# ---- the facts themselves --------------------------------------------------------------

def test_not_a_duplicate(store):
    edit_invoice(store, duplicate_of=None)
    assert compute_risk_features(store, store.invoices[INV_0412]).duplicate_detected is False


def test_total_mismatch_comes_from_extractor_issue_codes(store):
    edit_invoice(store, extraction_issues=["TOTAL_MISMATCH"])
    assert compute_risk_features(store, store.invoices[INV_0412]).invoice_total_mismatch is True


def test_iban_different_from_verified_account_is_a_mismatch(store):
    edit_fields(store, iban="EG430019000500000000263180009")  # another vendor's account
    assert compute_risk_features(store, store.invoices[INV_0412]).bank_account_mismatch is True


def test_stored_iban_with_spaces_still_matches(store):
    spaced = "EG38 0019 0005 0000 0000 2631 8000 2"
    store.bank_accounts[1] = store.bank_accounts[1].model_construct(**{**store.bank_accounts[1].model_dump(), "iban": spaced})
    assert compute_risk_features(store, store.invoices[INV_0412]).bank_account_mismatch is False


def test_no_iban_on_invoice_is_unknown(store):
    edit_fields(store, iban=None)
    assert compute_risk_features(store, store.invoices[INV_0412]).bank_account_mismatch is None


def test_vendor_with_account_on_hold_is_pending(store):
    edit_invoice(store, vendor_id=EGPACK)
    assert store.bank_accounts[ACC_EGPACK_NEW].status == BankAccountStatus.ON_HOLD
    assert compute_risk_features(store, store.invoices[INV_0412]).vendor_change_pending is True


def test_extractor_ocr_confidence_wins_over_field_confidence(store):
    edit_invoice(store, ocr_confidence=0.5)
    assert compute_risk_features(store, store.invoices[INV_0412]).ocr_confidence == 0.5


def test_foreign_currency_amount_is_unknown(store):
    edit_fields(store, currency="USD")
    assert compute_risk_features(store, store.invoices[INV_0412]).invoice_total_egp is None


def test_invoice_without_extracted_fields(store):
    edit_invoice(store, fields=None, vendor_id=NILE)
    f = compute_risk_features(store, store.invoices[INV_0412])
    assert f.invoice_total_mismatch is None and f.bank_account_mismatch is None and f.invoice_total_egp is None
    assert f.ocr_confidence is None


def test_amount_stays_decimal(store):
    assert compute_risk_features(store, store.invoices[INV_0412]).invoice_total_egp == Decimal("15400.00")
