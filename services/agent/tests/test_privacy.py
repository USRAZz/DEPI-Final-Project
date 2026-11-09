from ai_core.llm import LLM, PROVIDERS
from ai_core.privacy import find_ibans, find_tax_ids, mask_messages, mask_sensitive

IBAN = "EG380019000500000000263180002"


def test_iban_masked_with_or_without_spaces():
    spaced = " ".join(IBAN[i:i + 4] for i in range(0, len(IBAN), 4))
    for v in (IBAN, spaced):
        out = mask_sensitive(f"pay to {v} now")
        assert "[IBAN]" in out and "2631" not in out


def test_arabic_digits_are_normalised_before_masking():
    arabic = "رقم الحساب EG٣٨٠٠١٩٠٠٠٥٠٠٠٠٠٠٠٠٢٦٣١٨٠٠٠٢"
    assert "[IBAN]" in mask_sensitive(arabic)


def test_tax_id_masked_only_next_to_a_tax_label():
    assert mask_sensitive("Tax Reg. No: 123-456-789") == "Tax Reg. No: [TAX_ID]"
    assert mask_sensitive("رقم التسجيل الضريبي ١٢٣٤٥٦٧٨٩").endswith("[TAX_ID]")
    assert mask_sensitive("Invoice 123456789 total 500") == "Invoice 123456789 total 500"


def test_phone_and_email_masked():
    out = mask_sensitive("call 01012345678 or +20 100 123 4567, mail a.b@example.com")
    assert out.count("[PHONE]") == 2 and "[EMAIL]" in out


def test_amounts_and_dates_are_left_alone():
    s = "Total 12,500.00 EGP on 2026-10-03, invoice A-1001"
    assert mask_sensitive(s) == s


def test_find_ibans_keeps_only_valid_checksums():
    bad = IBAN[:-1] + "3"
    assert find_ibans(f"{IBAN} and {bad}") == [IBAN]


def test_find_tax_ids():
    assert find_tax_ids("VAT number 123 456 789") == ["123456789"]


def test_mask_messages_covers_text_parts_and_keeps_images():
    msgs = [{"role": "user", "content": [{"type": "text", "text": IBAN}, {"type": "image_url", "image_url": {"url": "x"}}]}]
    out = mask_messages(msgs)
    assert out[0]["content"][0]["text"] == "[IBAN]" and out[0]["content"][1] == msgs[0]["content"][1]
    assert msgs[0]["content"][0]["text"] == IBAN  # original untouched


def test_only_openai_is_allowed(monkeypatch):
    assert list(PROVIDERS) == ["openai"]
    monkeypatch.setenv("GROQ_API_KEY", "x")
    try:
        LLM("groq", "m")
    except ValueError as e:
        assert "unknown provider" in str(e)
    else:
        raise AssertionError("groq must be rejected")


def test_llm_chat_sends_masked_messages(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    llm = LLM("openai", "m")
    sent = {}

    class R:
        choices = [type("C", (), {"message": type("M", (), {"content": "ok"})(), "finish_reason": "stop"})()]
        usage = None

    monkeypatch.setattr(llm, "_create", lambda kw: sent.update(kw) or R())
    llm.chat([{"role": "user", "content": f"IBAN {IBAN}"}])
    assert sent["messages"][0]["content"] == "IBAN [IBAN]"
