"""Offline tests for the AI part: a scripted FakeLLM replaces the real API (no key, no cost).
Run from the repo root:  python -m pytest tests/test_ai_part.py -q"""
import pytest

from ai_core.llm import BudgetExceeded, StructuredOutputError
from ai_core.prompts import load_prompt, untrusted
from services.agent.app.agent_loop import run_agent
from services.agent.app.router import Route, route_request
from services.agent.app.tools import Context, MockBackend, ToolRegistry, calculate, search_policies
from services.extractor.app import pipeline
from services.extractor.app.schemas import InvoiceFields


class FakeLLM:
    def __init__(self, *outputs):
        self.outputs = list(outputs)

    def structured(self, messages, schema, *, retries=1, budget=None):
        if not self.outputs:
            raise StructuredOutputError("script exhausted")
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return schema.model_validate(out)

    def chat(self, messages, **kw):
        return "partial answer"


def tool(name, **args):
    return {"thought": "need data", "action": "tool", "tool": name, "args": args}


def final(text):
    return {"thought": "done", "action": "final", "answer": text}


def registry():
    return ToolRegistry(MockBackend())


# ---------- routing
def test_attachment_without_text_skips_the_llm():
    assert route_request("", has_attachment=True, llm=FakeLLM()).route == Route.invoice_upload


def test_low_confidence_becomes_unclear():
    d = route_request("hmm", llm=FakeLLM({"route": "finance_question", "confidence": 0.3, "language": "ar"}))
    assert d.route == Route.unclear and d.clarifying_question


def test_llm_failure_falls_back_to_unclear():
    assert route_request("x", llm=FakeLLM(StructuredOutputError("bad"))).route == Route.unclear


# ---------- prompts
def test_missing_prompt_variable_raises():
    with pytest.raises(KeyError):
        load_prompt("router")


def test_untrusted_tag_is_random():
    a, b = untrusted("hi"), untrusted("hi")
    assert a != b and "hi" in a


# ---------- tools
def test_calculate_is_safe():
    assert calculate("2 + 3*4") == 14
    with pytest.raises(ValueError):
        calculate("__import__('os').system('dir')")
    with pytest.raises(ValueError):
        calculate("9**9**9")


def test_search_policies_finds_rule(tmp_path, monkeypatch):
    f = tmp_path / "p.yaml"
    f.write_text("limits:\n  - name: dual approval\n    above: 10000\n    approvers: 2\n", encoding="utf-8")
    monkeypatch.setenv("POLICIES_FILE", str(f))
    assert "dual" in str(search_policies("dual approval limit"))


# ---------- invoice pipeline
def test_arabic_digits_are_normalized():
    f = InvoiceFields(vendor_name="X", invoice_number="١٢٣", total_amount="١٬٢٣٤٫٥٠", currency="جنيه")
    assert f.total_amount == 1234.5 and f.invoice_number == "123" and f.currency == "EGP"


def test_gate_flags_total_mismatch():
    f = InvoiceFields(vendor_name="X", invoice_number="1", subtotal=100, tax_amount=14, total_amount=120)
    assert any("total" in i for i in pipeline.check_fields(f))


FIELDS = {"vendor_name": "Nile Office", "invoice_number": "A-1", "invoice_date": "2026-10-03", "currency": "EGP",
          "subtotal": 100, "tax_amount": 14, "total_amount": 114, "line_items": [{"description": "Paper", "total": 100}]}
CATEGORY = {"category": "office_supplies", "confidence": 0.9, "reason": "paper"}


def test_pipeline_ready_then_duplicate(tmp_path):
    inv = tmp_path / "inv.txt"
    inv.write_text("Nile Office invoice A-1 total 114 EGP, paper 100 + tax 14", encoding="utf-8")
    seen = {}
    r1 = pipeline.process_invoice(inv, llm_extract=FakeLLM(FIELDS), llm_categorize=FakeLLM(CATEGORY), seen=seen)
    assert r1.status == "READY" and r1.category.category == "office_supplies"
    r2 = pipeline.process_invoice(inv, llm_extract=FakeLLM(FIELDS), llm_categorize=FakeLLM(CATEGORY), seen=seen)
    assert r2.status == "FLAGGED" and r2.duplicate_of


def test_pipeline_fails_cleanly_when_extraction_fails(tmp_path):
    inv = tmp_path / "inv.txt"
    inv.write_text("some invoice text that is long enough to pass", encoding="utf-8")
    r = pipeline.process_invoice(inv, llm_extract=FakeLLM(StructuredOutputError("bad json")), llm_categorize=FakeLLM(), seen={})
    assert r.status == "FAILED" and r.fields is None


# ---------- agent loop
def test_agent_uses_a_tool_then_answers():
    llm = FakeLLM(tool("get_invoices", status="FLAGGED"), final("INV-003 is flagged."))
    r = run_agent("which are flagged?", Context(), llm=llm, registry=registry())
    assert r.status == "done" and r.tools_used == ["get_invoices"] and "INV-003" in r.answer


def test_agent_stops_at_the_step_limit():
    llm = FakeLLM(*[tool("calculate", expression="1+1")] * 20)
    r = run_agent("loop", llm=llm, registry=registry(), max_steps=3)
    assert r.status == "checkpoint" and r.steps == 3


def test_agent_recovers_from_unknown_tool():
    llm = FakeLLM(tool("delete_everything"), final("Sorry, I cannot do that."))
    r = run_agent("x", llm=llm, registry=registry())
    assert r.status == "done" and r.tools_used == []


def test_budget_exceeded_gives_a_checkpoint():
    r = run_agent("x", llm=FakeLLM(BudgetExceeded("tokens")), registry=registry())
    assert r.status == "checkpoint"