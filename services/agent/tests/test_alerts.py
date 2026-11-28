"""Every flagged or risky invoice the assistant used comes back with WHY (ChatResponse.alerts + a block under the
answer), built by code from the tool results. Offline: scripted fake LLMs."""
import re

import app.main as main
from app.alerts import alerts_text, build_alerts
from app.explain import MEANINGS
from app.tools import Context, MockBackend, ToolRegistry
from securefin_contracts import ChatRequest


class Scripted:
    def __init__(self, *outputs):
        self.outputs = list(outputs)

    def structured(self, messages, schema, **kw):
        return schema.model_validate(self.outputs.pop(0))

    def chat(self, messages, **kw):
        return "partial"


class Router:
    def __init__(self, route="finance_question", language="en"):
        self.route, self.language = route, language

    def structured(self, messages, schema, **kw):
        return schema.model_validate({"route": self.route, "confidence": 0.9, "language": self.language})


def tool(name, **args):
    return {"thought": "t", "action": "tool", "tool": name, "args": args}


def final(answer):
    return {"thought": "t", "action": "final", "answer": answer}


def chat(message, *steps, language="en"):
    return main.handle_chat(ChatRequest(message=message), Context(), router_llm=Router(language=language),
                            agent_llm=Scripted(*steps), registry=ToolRegistry(MockBackend())).response


def test_a_flagged_invoice_comes_back_with_its_reason_even_if_the_model_gives_none():
    r = chat("Which invoices are flagged?", tool("get_invoices", status="FLAGGED"), final("Invoices 3 and 5 are flagged."))
    by_id = {a.invoice_id: a for a in r.alerts}
    assert set(by_id) == {3, 5}
    assert [x.code for x in by_id[3].reasons] == ["DUPLICATE_INVOICE"] and by_id[3].level.value == "high"
    # invoice 5: the risk rule and the invoice reader's own issue, both explained
    assert [x.code for x in by_id[5].reasons] == ["INVOICE_TOTAL_MISMATCH", "TOTAL_MISMATCH"]
    assert "Why these invoices have alerts:" in r.answer and "same vendor and invoice number" in r.answer
    assert "high risk (70/100)" in r.answer and "subtotal plus tax" in r.answer


def test_reasons_are_in_arabic_for_arabic_users():
    r = chat("إيه الفواتير اللي عليها تنبيه؟", tool("get_invoices", status="FLAGGED"), final("الفاتورتين 3 و 5."),
             language="ar")
    assert "سبب التنبيهات:" in r.answer and "مخاطر عالية (70/100)" in r.answer and "نفس رقم فاتورة" in r.answer
    assert all(re.search(r"[؀-ۿ]", x.text) for a in r.alerts for x in a.reasons)


def test_a_risk_score_the_model_read_becomes_an_alert():
    r = chat("Why is invoice 3 risky?", tool("get_risk_score", invoice_id=3), final("It looks like a duplicate."))
    assert [a.invoice_id for a in r.alerts] == [3] and r.sources == ["get_risk_score"]


def test_clean_invoices_give_no_alerts_and_no_block():
    r = chat("Show invoices from Delta Telecom", tool("get_invoices", vendor_name="Delta"), final("Invoice 7781."))
    assert r.alerts == [] and "alerts" not in r.answer and r.sources == ["get_invoices"]


def test_a_flagged_invoice_without_any_recorded_reason_says_so():
    class NoReason(MockBackend):
        INVOICES = [{"id": 9, "vendor_name": "X", "invoice_number": "N-9", "invoice_date": "2026-10-01",
                     "total_amount": 10.0, "status": "FLAGGED"}]
        RISK = {}

    calls = [("get_invoices", {}, NoReason.INVOICES)]
    [alert] = build_alerts(calls, NoReason(), Context(), "en")
    assert alert.reasons[0].code == "FLAGGED" and "no reason was recorded" in alert.reasons[0].text
    assert alert.level.value == "low"


def test_the_backend_failing_still_returns_the_invoice_codes():
    class Down(MockBackend):
        def get_risk_score(self, ctx, invoice_id):
            raise RuntimeError("api down")

    inv = {"id": 5, "invoice_number": "GP-310", "status": "FLAGGED", "extraction_issues": ["SUSPICIOUS_INSTRUCTIONS"]}
    [alert] = build_alerts([("get_invoices", {}, [inv])], Down(), Context(), "en")
    assert [x.code for x in alert.reasons] == ["SUSPICIOUS_INSTRUCTIONS"] and "hidden instructions" in alert.reasons[0].text


def test_every_invoice_reader_code_is_explained_in_both_languages():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[3]
    source = (root / "services/extractor/app/pipeline.py").read_text(encoding="utf-8")
    codes = set(re.findall(r'^\s+"([A-Z_]{6,})": "', source, re.M)) | {"SCHEMA_INVALID", "SUSPICIOUS_INSTRUCTIONS"}
    assert codes and codes <= set(MEANINGS), codes - set(MEANINGS)
    assert all(set(v) == {"ar", "en"} for v in MEANINGS.values())


def test_alerts_text_is_empty_without_alerts():
    assert alerts_text([], "en") == ""


def test_report_alerts_section_carries_the_reasons():
    from datetime import date

    from app import reports

    def boom():
        raise RuntimeError("no llm")

    plan = {"sections": ["anomalies"], "date_from": "2026-09-01", "date_to": "2026-10-31"}
    roles = {"report_orchestrator": lambda: Scripted(plan), "report_worker": boom, "report_writer": boom,
             "report_evaluator": boom}
    r = reports.generate_report("تقرير التنبيهات من سبتمبر لأكتوبر 2026", backend=MockBackend(),
                                today=date(2026, 11, 27), llms=roles)
    flagged = {f["invoice_number"]: f for f in r.sections[0].facts["flagged"]}
    assert set(flagged) == {"A-1001", "GP-310"}
    assert "نفس رقم فاتورة" in flagged["A-1001"]["reasons"][0]
    assert "مش مظبوطة" in r.markdown and "نفس رقم فاتورة" in r.markdown  # also in the fixed wording
