"""Reports (pattern ④) and Jev model routing. Offline: every LLM role is a scripted fake, nothing leaves the process."""
from datetime import date

import app.main as main
import httpx
import openai
import pytest
from app import reports
from app.tools import MockBackend
from fastapi.testclient import TestClient

from ai_core import llm as llm_mod
from ai_core.llm import Budget, BudgetExceeded

TODAY = date(2026, 11, 27)
OCT = {"date_from": "2026-10-01", "date_to": "2026-10-31"}


class Scripted:
    """structured() answers from a list; a callable item is called with the messages (to build a reply)."""

    def __init__(self, *outputs):
        self.outputs, self.calls = list(outputs), []

    def structured(self, messages, schema, **kw):
        self.calls.append(messages)
        out = self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]
        if isinstance(out, Exception):
            raise out
        return schema.model_validate(out(messages) if callable(out) else out)


def no_llm():
    raise AssertionError("this role must not be called")


def roles(orchestrator=None, worker=None, writer=None, evaluator=None):
    made = {"report_orchestrator": orchestrator, "report_worker": worker, "report_writer": writer,
            "report_evaluator": evaluator}
    return {k: (lambda v=v: v) if v is not None else no_llm for k, v in made.items()}


PLAN = {"sections": ["spending_summary", "top_vendors"], **OCT, "title": "October spending"}
WORKER = {"heading": "Section", "body": "Written from the facts."}


def draft(**over):
    d = {"title": "October 2026 spending", "summary": "15,900 EGP was paid and 28,400 EGP invoiced.",
         "sections": [{"key": "spending_summary", "heading": "Spending", "body": "Paid 15,900 EGP in 2 payments."},
                      {"key": "top_vendors", "heading": "Vendors", "body": "Nile Office Supplies: 25,000 EGP (88%)."}]}
    return {**d, **over}


def run(request="Spending report for October 2026", **kw):
    return reports.generate_report(request, backend=MockBackend(), today=TODAY, **kw)


# ---- the happy path ---------------------------------------------------------------------------------------------

def test_a_draft_that_matches_the_data_and_passes_review_is_returned():
    r = run(llms=roles(Scripted(PLAN), Scripted(WORKER), Scripted(draft()), Scripted({"passes": True})))
    assert r.quality == "passed" and r.rounds == 1
    assert [s.key for s in r.sections] == ["spending_summary", "top_vendors"]
    assert r.sections[0].facts["paid_total"] == 15900 and r.sections[0].facts["invoiced_total"] == 28400
    assert r.markdown.startswith("# October 2026 spending") and "## Vendors" in r.markdown


def test_workers_get_only_their_own_facts_as_tagged_data():
    worker = Scripted(WORKER)
    run(llms=roles(Scripted(PLAN), worker, Scripted(draft()), Scripted({"passes": True})))
    user_msgs = [m[1]["content"] for m in worker.calls]
    assert len(user_msgs) == 2 and all("<UNTRUSTED_" in m for m in user_msgs)
    assert any("paid_total" in m and "vendors" not in m for m in user_msgs)


# ---- evaluator-optimizer ----------------------------------------------------------------------------------------

def test_an_invented_number_is_sent_back_and_the_fixed_draft_passes():
    bad = draft(summary="We paid 999,999 EGP this month.")
    writer = Scripted(bad, draft())
    r = run(llms=roles(Scripted(PLAN), Scripted(WORKER), writer, Scripted({"passes": True})))
    assert r.quality == "passed" and r.rounds == 2
    feedback = writer.calls[1][1]["content"]
    assert "999999" in feedback and "numbers not in the data" in feedback


def test_a_number_that_never_matches_the_data_ends_in_the_fixed_wording():
    bad = draft(summary="Total spending was 1,234,567 EGP.")
    r = run(llms=roles(Scripted(PLAN), Scripted(WORKER), Scripted(bad), Scripted({"passes": True})))
    assert r.quality == "fallback" and r.rounds == reports.MAX_ROUNDS
    assert "1,234,567" not in r.markdown and "15,900 EGP" in r.markdown


def test_evaluator_feedback_after_three_rounds_keeps_the_checked_text_and_says_so():
    r = run(llms=roles(Scripted(PLAN), Scripted(WORKER), Scripted(draft()),
                       Scripted({"passes": False, "feedback": ["summary: mention the vendors"]})))
    assert r.quality == "numbers_checked" and r.rounds == 3 and "mention the vendors" in r.notes[-1]


def test_a_missing_or_reordered_section_is_refused():
    one = draft(sections=draft()["sections"][:1])
    r = run(llms=roles(Scripted(PLAN), Scripted(WORKER), Scripted(one), Scripted({"passes": True})))
    assert r.quality == "fallback" and [s.key for s in r.sections] == ["spending_summary", "top_vendors"]


def test_arabic_request_needs_arabic_text_but_vendor_names_may_stay_english():
    ar = draft(title="مصروفات أكتوبر 2026", summary="اتدفع 15,900 جنيه.",
               sections=[{"key": "spending_summary", "heading": "المصروفات", "body": "المدفوع 15,900 جنيه في 2 دفعة."},
                         {"key": "top_vendors", "heading": "الموردين", "body": "Nile Office Supplies: 25,000 جنيه."}])
    r = run("تقرير مصروفات أكتوبر 2026",
            llms=roles(Scripted(PLAN), Scripted(WORKER), Scripted(ar), Scripted({"passes": True})))
    assert r.quality == "passed" and r.language.value == "ar"
    r = run("تقرير مصروفات أكتوبر 2026",
            llms=roles(Scripted(PLAN), Scripted(WORKER), Scripted(draft()), Scripted({"passes": True})))
    assert r.quality == "fallback" and "جنيه" in r.markdown  # an English draft never reaches an Arabic user


# ---- orchestrator -----------------------------------------------------------------------------------------------

def test_orchestrator_picks_sections_at_run_time():
    plan = {"sections": ["anomalies", "unpaid_invoices", "trend"], **OCT}
    r = run(llms=roles(Scripted(plan), Scripted(WORKER), Scripted(RuntimeError("down"))))
    assert [s.key for s in r.sections] == ["anomalies", "unpaid_invoices", "trend"] and r.quality == "fallback"
    flagged = r.sections[0].facts["flagged"]
    assert [f["invoice_number"] for f in flagged] == ["A-1001"] and "same vendor" in flagged[0]["reasons"][0]
    assert r.sections[1].facts["unpaid"] == []  # invoices 1 and 2 are paid, 3 is flagged
    assert r.sections[2].facts["months"] == [{"month": "2026-10", "invoiced": 28400, "paid": 15900}]


def test_unknown_sections_and_bad_periods_are_corrected():
    plan = {"sections": ["delete_audit_log", "categories"], "date_from": "2026-12-01", "date_to": "2025-01-01"}
    r = run(llms=roles(Scripted(plan), Scripted(WORKER), Scripted(RuntimeError("down"))))
    assert [s.key for s in r.sections] == ["categories"]
    assert (r.date_from, r.date_to) == (date(2026, 10, 1), date(2026, 10, 31))  # previous month
    assert any("unknown sections" in n for n in r.notes) and any("not valid" in n for n in r.notes)


def test_a_future_end_date_is_clamped_to_today():
    plan = {"sections": ["spending_summary"], "date_from": "2026-11-01", "date_to": "2026-12-31"}
    r = run(llms=roles(Scripted(plan)))
    assert r.date_to == TODAY


def test_orchestrator_failure_uses_defaults_and_says_so():
    r = run(llms=roles(Scripted(RuntimeError("down")), Scripted(RuntimeError("down"))))
    assert [s.key for s in r.sections] == reports.DEFAULT_SECTIONS and r.quality == "fallback"
    assert any("could not be planned" in n for n in r.notes)


def test_empty_period_needs_no_writer():
    plan = {"sections": ["spending_summary"], "date_from": "2026-01-01", "date_to": "2026-01-31"}
    r = run(llms=roles(Scripted(plan)))
    assert r.quality == "fallback" and "no invoices or payments" in r.notes[-1] and "0 EGP" in r.markdown


def test_cost_limit_gives_the_fixed_wording():
    r = run(llms=roles(Scripted(PLAN), Scripted(BudgetExceeded("tokens"))), budget=Budget(max_tokens=10))
    assert r.quality == "fallback" and "cost/time limit" in r.notes[-1]


# ---- numbers check ----------------------------------------------------------------------------------------------

def test_numbers_check_accepts_the_usual_ways_to_write_a_fact():
    facts = {"spending_summary": {"paid_total": 15900, "share_pct": 88.0, "invoice_number": "A-1001",
                                  "invoice_date": "2026-10-03"}}
    allowed = reports.allowed_numbers(facts, date(2026, 10, 1), date(2026, 10, 31))
    for text in ["15,900", "15900", "١٥٬٩٠٠", "15,900.00", "88%", "88.0", "A-1001", "3 October 2026", "31"]:
        assert all(n in allowed for n in reports._numbers(text)), text
    assert not all(n in allowed for n in reports._numbers("15,901"))


# ---- endpoints and chat -------------------------------------------------------------------------------------------

def test_reports_endpoint(monkeypatch):
    monkeypatch.setattr(main, "generate_report", lambda request, ctx: run(request, llms=roles(
        Scripted(PLAN), Scripted(WORKER), Scripted(draft()), Scripted({"passes": True}))))
    body = TestClient(main.app).post("/v1/reports", json={"request": "Spending report for October 2026"}).json()
    assert body["quality"] == "passed" and body["sections"][0]["facts"]["paid_total"] == 15900


def test_chat_report_route_returns_the_markdown():
    from app.router import Route
    from securefin_contracts import ChatRequest

    class R:
        def structured(self, messages, schema, **kw):
            return schema.model_validate({"route": "report_request", "confidence": 0.9, "language": "en"})

    out = main.handle_chat(ChatRequest(message="Spending report for October 2026"), main.Context(), router_llm=R(),
                           report_llms=roles(Scripted(PLAN), Scripted(WORKER), Scripted(draft()),
                                             Scripted({"passes": True})), report_backend=MockBackend())
    assert out.route == Route.report_request and out.response.answer.startswith("# October 2026 spending")
    assert out.response.proposed_actions == [] and out.report.quality == "passed"


# ---- Jev model routing (ai_core/llm.py) -------------------------------------------------------------------------

@pytest.fixture
def jev(monkeypatch):
    for k in ("LLM_ROUTING", "JEV_MODELS", "JEV_EXCLUDED_MODELS", "JEV_COST_TIER", "AGENT_MODEL", "AGENT_ROUTING",
              "REPORT_EVALUATOR_JEV_COST_TIER", "JEV_FALLBACK_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-used")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setenv("LLM_ROUTING", "jev")
    monkeypatch.setattr(llm_mod, "_jev_down_until", 0.0)  # every test starts with Jev "up"
    return monkeypatch


def test_after_jev_refuses_the_next_calls_skip_it_for_a_while(jev):
    client = llm_mod.get_llm("agent")
    sent = []

    def create(**kw):
        sent.append(kw["model"])
        if kw["model"] == "typesafe/jev-router":
            raise _status_error(404)
        return _Resp(kw["model"])

    client.client.chat.completions.create = create
    client.chat([{"role": "user", "content": "one"}])
    client.chat([{"role": "user", "content": "two"}])
    assert sent == ["typesafe/jev-router", "openai/gpt-4o-mini", "openai/gpt-4o-mini"]
    jev.setattr(llm_mod, "_jev_down_until", 0.0)  # the wait is over: Jev is tried again
    client.chat([{"role": "user", "content": "three"}])
    assert sent[-2:] == ["typesafe/jev-router", "openai/gpt-4o-mini"]


def test_jev_routing_uses_the_router_model_with_a_tier_per_role(jev):
    agent, evaluator = llm_mod.get_llm("agent"), llm_mod.get_llm("report_evaluator")
    assert agent.model == "typesafe/jev-router" and agent.provider == "openrouter"
    assert agent.extra_body == {"plugins": [{"id": "jev-router", "cost_tier": "medium"}]}
    assert evaluator.extra_body["plugins"][0]["cost_tier"] == "high"
    assert agent.fallback_model == "openai/gpt-4o-mini"


def test_jev_pool_limits_and_overrides(jev):
    jev.setenv("JEV_MODELS", "openai/*, google/*")
    jev.setenv("JEV_EXCLUDED_MODELS", "*opus*")
    jev.setenv("REPORT_EVALUATOR_JEV_COST_TIER", "medium")
    plugin = llm_mod.get_llm("report_evaluator").extra_body["plugins"][0]
    assert plugin == {"id": "jev-router", "cost_tier": "medium", "models": ["openai/*", "google/*"],
                      "excluded_models": ["*opus*"]}


def test_a_fixed_model_for_a_role_wins_over_jev(jev):
    jev.setenv("AGENT_MODEL", "openai/gpt-4o")
    assert llm_mod.get_llm("agent").model == "openai/gpt-4o"


def test_bad_settings_are_refused(jev):
    jev.setenv("JEV_COST_TIER", "cheapest")
    with pytest.raises(ValueError):
        llm_mod.get_llm("router")
    jev.setenv("LLM_ROUTING", "magic")
    jev.delenv("JEV_COST_TIER")
    with pytest.raises(ValueError):
        llm_mod.get_llm("router")


class _Choice:
    def __init__(self, text):
        self.message, self.finish_reason = type("M", (), {"content": text})(), "stop"


class _Resp:
    def __init__(self, model):
        self.model, self.choices, self.usage = model, [_Choice('{"ok": true}')], None


def _status_error(code):
    resp = httpx.Response(code, request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"))
    return openai.APIStatusError("router unavailable", response=resp, body=None)


def test_the_chosen_model_is_recorded_and_the_plugin_is_sent(jev):
    client = llm_mod.get_llm("agent")
    sent = []
    client.client.chat.completions.create = lambda **kw: sent.append(kw) or _Resp("google/gemini-2.5-flash")
    client.chat([{"role": "user", "content": "hi"}])
    assert sent[0]["model"] == "typesafe/jev-router" and sent[0]["extra_body"]["plugins"][0]["id"] == "jev-router"
    assert dict(client.usage.models) == {"google/gemini-2.5-flash": 1}


def test_router_unavailable_falls_back_once_to_the_fixed_model(jev):
    client = llm_mod.get_llm("agent")
    sent = []

    def create(**kw):
        sent.append(kw)
        if kw["model"] == "typesafe/jev-router":
            raise _status_error(503)
        return _Resp(kw["model"])

    client.client.chat.completions.create = create
    client.chat([{"role": "user", "content": "hi"}])
    assert [k["model"] for k in sent] == ["typesafe/jev-router", "openai/gpt-4o-mini"]
    assert "extra_body" not in sent[1] and dict(client.usage.models) == {"openai/gpt-4o-mini": 1}


def test_other_errors_are_not_hidden_by_the_fallback(jev):
    client = llm_mod.get_llm("agent")

    def create(**kw):
        raise _status_error(401)

    client.client.chat.completions.create = create
    with pytest.raises(openai.APIStatusError):
        client.chat([{"role": "user", "content": "hi"}])
