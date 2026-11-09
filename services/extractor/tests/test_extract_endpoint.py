from datetime import date

import app.main as main
import pytest
from app.schemas import CategoryResult, ExtractionResult, InvoiceFields
from fastapi.testclient import TestClient

client = TestClient(main.app)
FIELDS = InvoiceFields(vendor_name="Nile Paper", invoice_number="A-1", invoice_date=date(2026, 10, 3),
                       total_amount=114, subtotal=100, tax_amount=14,
                       iban="EG380019000500000000263180002",
                       line_items=[{"description": "Paper", "quantity": 2, "unit_price": 50, "total": 100},
                                   {"description": "Delivery", "total": 14}])


@pytest.fixture
def result(monkeypatch):
    def install(r: ExtractionResult):
        monkeypatch.setattr(main, "process_invoice", lambda path: r)
    return install


def upload(name="inv.pdf", body=b"%PDF-1.4 fake"):
    return client.post("/v1/extract", files={"file": (name, body, "application/pdf")})


def test_ready_invoice_maps_to_validated_invoice_data(result):
    result(ExtractionResult(status="READY", fields=FIELDS, ocr_confidence=0.96,
                            category=CategoryResult(category="office_supplies", confidence=0.9)))
    r = upload().json()
    assert r["status"] == "VALIDATED" and r["ocr_confidence"] == 0.96 and r["category"] == "office_supplies"
    assert r["data"]["vendor"] == "Nile Paper" and r["data"]["amount"] == "114.00"
    assert r["data"]["iban"] == "EG380019000500000000263180002"
    assert r["data"]["line_items"] == [
        {"description": "Paper", "quantity": "2.00", "unit_price": "50.00"},
        {"description": "Delivery", "quantity": "1", "unit_price": "14.00"},
    ]


def test_flagged_keeps_issue_codes(result):
    result(ExtractionResult(status="FLAGGED", fields=FIELDS, issue_codes=["TOTAL_MISMATCH"]))
    r = upload().json()
    assert r["status"] == "FLAGGED" and r["issue_codes"] == ["TOTAL_MISMATCH"]


def test_missing_date_needs_review_without_data(result):
    result(ExtractionResult(status="READY", fields=FIELDS.model_copy(update={"invoice_date": None})))
    r = upload().json()
    assert r["status"] == "NEEDS-REVIEW" and r["data"] is None and "SCHEMA_INVALID" in r["issue_codes"]


def test_failed_extraction_needs_review(result):
    result(ExtractionResult(status="FAILED", issues=["OCR failed"]))
    r = upload().json()
    assert r == {"status": "NEEDS-REVIEW", "data": None, "issue_codes": [], "ocr_confidence": None, "category": None}


def test_unsupported_type_is_rejected(result):
    result(ExtractionResult(status="FAILED"))
    assert upload("inv.exe").status_code == 415


def test_too_large_file_is_rejected(result):
    result(ExtractionResult(status="FAILED"))
    assert upload(body=b"x" * (main.MAX_BYTES + 1)).status_code == 413
