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
    monkeypatch.setitem(ocr.ENGINES, "tesseract", lambda im: ("text", 0.42))
    assert ocr.extract_text_and_confidence(img) == ("text", 0.42)


def test_paddleocr_is_the_default_engine(tmp_path, monkeypatch):
    img = tmp_path / "inv.png"
    Image.new("RGB", (20, 20), "white").save(img)
    monkeypatch.delenv("OCR_ENGINE", raising=False)
    monkeypatch.setitem(ocr.ENGINES, "paddleocr", lambda im: ("paddle text", 0.97))
    assert ocr.extract_text_and_confidence(img) == ("paddle text", 0.97)


def test_vision_engine_refused_without_explicit_opt_in(tmp_path, monkeypatch):
    img = tmp_path / "inv.png"
    Image.new("RGB", (20, 20), "white").save(img)
    monkeypatch.setenv("OCR_ENGINE", "vision")
    monkeypatch.delenv("OCR_VISION_ALLOW_UNMASKED", raising=False)
    with pytest.raises(RuntimeError, match="unmasked"):
        ocr.extract_text_and_confidence(img)


def test_arabic_boxes_are_read_right_to_left_per_line():
    # two words on one line (x left->right: "B" then "A") and one word on the next line
    texts, boxes = ["B", "A", "C"], [[0, 0, 10, 10], [20, 0, 30, 10], [0, 30, 10, 40]]
    assert ocr.order_boxes(texts, boxes, right_to_left=True) == ["A B", "C"]
    assert ocr.order_boxes(texts, boxes, right_to_left=False) == ["B A", "C"]


class CapturingLLM(FakeLLM):
    def structured(self, messages, schema, *, retries=1, budget=None):
        self.seen = messages
        return super().structured(messages, schema, retries=retries, budget=budget)


def test_iban_and_tax_id_are_read_by_code_and_never_sent_to_the_llm(tmp_path):
    inv = tmp_path / "inv.txt"
    inv.write_text("Nile Office invoice A-1 total 114 EGP\nTax Reg. No: 123-456-789\n"
                   "IBAN: EG38 0019 0005 0000 0000 2631 8000 2\nPhone 01012345678", encoding="utf-8")
    llm = CapturingLLM({**FIELDS, "iban": None})
    r = pipeline.process_invoice(inv, llm_extract=llm, llm_categorize=FakeLLM(CATEGORY), seen={})
    sent = llm.seen[-1]["content"]
    assert "[IBAN]" in sent and "[TAX_ID]" in sent and "[PHONE]" in sent
    assert "2631" not in sent and "123-456-789" not in sent and "01012345678" not in sent
    assert r.fields.iban == "EG380019000500000000263180002" and r.fields.tax_id == "123456789"


def test_invalid_iban_on_the_invoice_is_flagged(tmp_path):
    inv = tmp_path / "inv.txt"
    inv.write_text("Nile Office invoice A-1 total 114 EGP\nIBAN: EG38 0019 0005 0000 0000 2631 8000 3",
                   encoding="utf-8")
    r = pipeline.process_invoice(inv, llm_extract=CapturingLLM({**FIELDS, "iban": None}),
                                 llm_categorize=FakeLLM(CATEGORY), seen={})
    assert r.fields.iban == "EG380019000500000000263180003"
    assert "IBAN_CHECKSUM_INVALID" in r.issue_codes


def test_paddle_output_is_merged_from_both_models(monkeypatch):
    models = {
        "ar": FakePaddle({"rec_texts": ["مصنع", "النيل"], "rec_scores": [0.9, 0.8],
                          "rec_boxes": [[0, 0, 10, 10], [20, 0, 30, 10]]}),
        "en": FakePaddle({"rec_texts": ["INV-1"], "rec_scores": [1.0], "rec_boxes": [[0, 20, 10, 30]]}),
    }
    monkeypatch.setattr(ocr, "_paddle_model", lambda lang: models[lang])
    text, conf = ocr._paddle(Image.new("RGB", (40, 40), "white"))
    assert text == "النيل مصنع\nINV-1" and conf == 0.9  # header pass read the same words: no duplicates


def test_header_pass_fixes_latin_letter_inside_arabic(monkeypatch):
    full = {"rec_texts": ["مصiع"], "rec_scores": [0.7], "rec_boxes": [[0, 0, 10, 10]]}
    header = {"rec_texts": ["مصنع"], "rec_scores": [0.95], "rec_boxes": [[0, 0, 10, 10]]}
    models = {"ar": FakePaddle(full, header=header), "en": FakePaddle({"rec_texts": [], "rec_boxes": []})}
    monkeypatch.setattr(ocr, "_paddle_model", lambda lang: models[lang])
    text, _ = ocr._paddle(Image.new("RGB", (40, 40), "white"))
    assert text == "مصنع"


def test_header_words_do_not_replace_a_whole_phrase():
    # STRESS3-013: the full page read one box, the crop read three word boxes, one of them surer
    full = [("شركة المرسى للخدمات", [924, 238, 1176, 289], 0.974)]
    crop = [("المرسى", [1019, 246, 1106, 285], 0.919), ("شركة", [1102, 245, 1170, 281], 0.996),
            ("للخدمات", [932, 248, 1019, 277], 0.995)]
    merged = ocr.merge_header(full, crop, page_height=1600)
    assert [t for t, _ in merged] == ["شركة المرسى للخدمات"]


def test_header_crop_needs_a_clear_margin():
    # STRESS-022: the crop dropped a letter ('السنبة') but scored a little higher
    full = [("شركة السنبلة للتجارة", [807, 247, 1000, 280], 0.953)]
    crop = [("شركة السنبة للتجارة", [802, 242, 1003, 285], 0.983)]
    assert [t for t, _ in ocr.merge_header(full, crop, page_height=1600)] == ["شركة السنبلة للتجارة"]


def test_letters_inside_amounts_are_fixed():
    assert ocr.fix_numbers("1,521.B0 EGP VAT 14%") == "1,521.80 EGP VAT 14%"
    assert ocr.fix_numbers("INV-2026-0042 SO20260000001234") == "INV-2026-0042 SO20260000001234"


class FakePaddle:
    """Returns page-pixel boxes; for the 2x header crop it returns them in crop pixels, like PaddleOCR."""

    def __init__(self, payload, header=None):
        self.payload, self.header = payload, header or payload

    def predict(self, arr):
        if arr.shape[0] == 40:  # the full test page
            return [_Res(self.payload)]
        boxes = [[v * ocr.HEADER_SCALE for v in b] for b in self.header.get("rec_boxes", [])]
        return [_Res({**self.header, "rec_boxes": boxes})]


class _Res:
    def __init__(self, payload):
        self.json = {"res": payload}
