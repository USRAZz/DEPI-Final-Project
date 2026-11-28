"""The agent's tools (BACKEND=api) against the REAL services/api routes and sample data, in-process.
No network and no LLM: the agent's model is a scripted fake; everything else is the production code path."""
from datetime import date

import httpx
from fastapi.testclient import TestClient
from securefin_contracts import ChatRequest

from services.agent.app import main as agent_main
from services.agent.app.reports import generate_report
from services.agent.app.tools import ApiBackend, Context, ToolRegistry
from services.api.app.main import create_app
from services.api.app.store import INV_0412, KARIM, OUTSIDER, seeded_store


class FakeGateway:  # the api needs one to start; these tests never approve or pay
    pass


def backend():
    api = TestClient(create_app(store=seeded_store(), gateway=FakeGateway()))

    def forward(req: httpx.Request) -> httpx.Response:  # the agent's HTTP request, answered by the real api app
        resp = api.request(req.method, req.url.path, params=req.url.params, headers=dict(req.headers))
        return httpx.Response(resp.status_code, content=resp.content, headers={"content-type": "application/json"})

    return ApiBackend("http://testserver", transport=httpx.MockTransport(forward))


class Scripted:
    def __init__(self, *outputs):
        self.outputs = list(outputs)

    def structured(self, messages, schema, **kw):
        return schema.model_validate(self.outputs.pop(0))

    def chat(self, messages, **kw):
        return "partial"


class Router:
    def structured(self, messages, schema, **kw):
        return schema.model_validate({"route": "finance_question", "confidence": 0.9, "language": "en"})


def test_flagged_invoice_from_the_api_comes_back_with_its_reasons():
    steps = [{"thought": "t", "action": "tool", "tool": "get_invoices", "args": {"status": "FLAGGED"}},
             {"thought": "t", "action": "final", "answer": "Invoice INV-2026-0412 from Nile Paper is flagged."}]
    out = agent_main.handle_chat(ChatRequest(message="Which invoices are flagged?"), Context(user_id=str(KARIM)),
                                 router_llm=Router(), agent_llm=Scripted(*steps), registry=ToolRegistry(backend()))
    [alert] = out.response.alerts
    assert alert.invoice_id == INV_0412 and alert.vendor == "Nile Paper" and alert.level.value == "high"
    assert "DUPLICATE_INVOICE" in [r.code for r in alert.reasons]
    assert "same vendor and invoice number" in out.response.answer


def test_another_companys_user_gets_nothing_through_the_agent():
    rows = backend().get_invoices(Context(user_id=str(OUTSIDER)), {})
    assert rows == []


def test_report_on_api_data_without_any_llm():
    def boom():
        raise RuntimeError("no llm in this test")

    plan = {"sections": ["spending_summary", "anomalies"], "date_from": "2026-10-01", "date_to": "2026-11-30"}
    llms = {"report_orchestrator": lambda: Scripted(plan), "report_worker": boom, "report_writer": boom,
            "report_evaluator": boom}
    r = generate_report("Report for October and November 2026", Context(user_id=str(KARIM)), backend=backend(),
                        today=date(2026, 11, 27), llms=llms)
    flagged = {f["invoice_id"]: f for f in r.sections[1].facts["flagged"]}
    assert set(flagged) == {INV_0412, 415} and r.quality == "fallback"
    assert "same vendor and invoice number" in flagged[INV_0412]["reasons"][0]
    # 415 is not flagged but scored medium with no rule: said as it is, not as "flagged"
    assert "rated this payment medium risk" in flagged[415]["reasons"][0]
    assert r.sections[0].facts["invoices_count"] == 5 and r.sections[0].facts["paid_total"] == 0
