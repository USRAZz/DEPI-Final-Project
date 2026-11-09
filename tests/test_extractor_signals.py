"""Signals the extractor hands to the api for the risk service: stable issue codes and OCR confidence."""
import pytest
from PIL import Image

from services.extractor.app import ocr, pipeline
from services.extractor.app.schemas import InvoiceFields
from tests.test_ai_part import CATEGORY, FIELDS, FakeLLM


def _fields(**kw):
    return InvoiceFields(**{"vendor_name": "X", "invoice_number": "1", **kw})


@pytest.mark.parametrize(("kw", "code"), [
    ({"subtotal": 100, "tax_amount": 14, "total_amount": 120}, "TOTAL_MISMATCH"),
    ({"total_amount": 0}, "NON_POSITIVE_TOTAL"),
    ({"subtotal": 100, "total_amount": 100, "line_items": [{"description": "a", "total": 60}]}, "LINE_ITEMS_MISMATCH"),
    ({"total_amount": 10, "invoice_date": "2026-10-10", "due_date": "2026-10-01"}, "DUE_BEFORE_INVOICE"),
    ({"total_amount": 10, "iban": "EG380019000500000000263180003"}, "IBAN_CHECKSUM_INVALID"),
])
def test_each_check_has_a_stable_code(kw, code):
    assert pipeline.check_field_codes(_fields(**kw)) == [code]


def test_messages_are_unchanged_for_existing_callers():
    f = _fields(subtotal=100, tax_amount=14, total_amount=120)
    assert pipeline.check_fields(f) == ["subtotal + tax does not equal total"]


def test_clean_invoice_has_no_codes():
    assert pipeline.check_field_codes(_fields(subtotal=100, tax_amount=14, total_amount=114)) == []


def test_pipeline_returns_codes_and_confidence(tmp_path):
    inv = tmp_path / "inv.txt"
    inv.write_text("Nile Office invoice A-1 total 120 EGP, paper 100 + tax 14", encoding="utf-8")
    bad = {**FIELDS, "total_amount": 120}
    seen = {}
    r = pipeline.process_invoice(inv, llm_extract=FakeLLM(bad), llm_categorize=FakeLLM(CATEGORY), seen=seen)
    assert r.status == "FLAGGED" and "TOTAL_MISMATCH" in r.issue_codes
    assert r.ocr_confidence is None  # .txt input: no OCR ran
    r2 = pipeline.process_invoice(inv, llm_extract=FakeLLM(bad), llm_categorize=FakeLLM(CATEGORY), seen=seen)
    assert "POSSIBLE_DUPLICATE" in r2.issue_codes


def test_pipeline_low_category_confidence_code(tmp_path):
    inv = tmp_path / "inv.txt"
    inv.write_text("Nile Office invoice A-1 total 114 EGP, paper 100 + tax 14", encoding="utf-8")
    low = {**CATEGORY, "confidence": 0.2}
    r = pipeline.process_invoice(inv, llm_extract=FakeLLM(FIELDS), llm_categorize=FakeLLM(low), seen={})
    assert r.issue_codes == ["LOW_CATEGORY_CONFIDENCE"]


def test_image_confidence_uses_the_engine_score(tmp_path, monkeypatch):
    img = tmp_path / "inv.png"
    Image.new("RGB", (20, 20), "white").save(img)
    monkeypatch.setenv("OCR_ENGINE", "tesseract")
    monkeypatch.setitem(ocr.ENGINES, "tesseract", lambda im: "text")
    monkeypatch.setitem(ocr.CONFIDENCE, "tesseract", lambda im: 0.42)
    assert ocr.extract_text_and_confidence(img) == ("text", 0.42)


def test_engine_without_score_gives_none(tmp_path, monkeypatch):
    img = tmp_path / "inv.png"
    Image.new("RGB", (20, 20), "white").save(img)
    monkeypatch.setenv("OCR_ENGINE", "vision")
    monkeypatch.setitem(ocr.ENGINES, "vision", lambda im: "text")
    assert ocr.extract_text_and_confidence(img) == ("text", None)
