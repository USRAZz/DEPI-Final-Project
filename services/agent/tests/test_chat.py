import app.main as main
import pytest
from app.agent_loop import AgentResult
from app.router import Route, RouteDecision
from fastapi.testclient import TestClient

client = TestClient(main.app)
GOOD = {"tool": "create_payment_request", "params": {"invoice_id": 3, "vendor_id": 1, "amount": "12500.00"},
        "rationale": "invoice 3 is due"}


@pytest.fixture
def wire(monkeypatch):
    def install(route=Route.finance_question, answer="Done.", proposal=None, language="en", clarify=None):
        seen = {}
        monkeypatch.setattr(main, "route_request", lambda msg: RouteDecision(
            route=route, confidence=0.9, language=language, clarifying_question=clarify))

        def fake_run(question, ctx, *, language):
            seen.update(question=question, ctx=ctx, language=language)
            return AgentResult(status="done", answer=answer, proposal=proposal)
        monkeypatch.setattr(main, "run_agent", fake_run)
        return seen
    return install


def test_valid_proposal_becomes_a_proposed_action(wire):
    wire(proposal=GOOD)
    r = client.post("/v1/chat", json={"message": "pay invoice 3"}).json()
    assert r["proposed_actions"] == [{"tool": "create_payment_request",
                                      "params": {"invoice_id": 3, "vendor_id": 1, "amount": "12500.00", "currency": "EGP"},
                                      "rationale": "invoice 3 is due"}]


@pytest.mark.parametrize("bad", [
    {**GOOD, "params": {**GOOD["params"], "iban": "EG380019000500000000263180002"}},   # no bank account allowed
    {**GOOD, "params": {**GOOD["params"], "amount": "-5"}},
    {**GOOD, "tool": "approve_payment"},
    {"type": "payment_request", "invoice_id": "INV-003", "beneficiary": "X"},           # old free-form shape
])
def test_invalid_proposal_is_dropped_and_user_is_told(wire, bad):
    wire(proposal=bad)
    r = client.post("/v1/chat", json={"message": "pay"}).json()
    assert r["proposed_actions"] == [] and "could not prepare a valid payment proposal" in r["answer"]


def test_dry_run_returns_no_proposals(wire):
    wire(proposal=GOOD)
    assert client.post("/v1/chat", json={"message": "pay", "mode": "dry_run"}).json()["proposed_actions"] == []


def test_unclear_request_asks_a_question_without_running_the_agent(wire):
    seen = wire(route=Route.unclear, clarify="What do you want to do?")
    r = client.post("/v1/chat", json={"message": "hmm"}).json()
    assert r == {"answer": "What do you want to do?", "proposed_actions": []} and seen == {}


def test_invoice_upload_points_to_the_upload_screen_in_arabic(wire):
    wire(route=Route.invoice_upload, language="ar")
    r = client.post("/v1/chat", json={"message": "عايز أرفع فاتورة"}).json()
    assert "شاشة الفواتير" in r["answer"]


def test_user_token_and_role_reach_the_tools(wire):
    seen = wire()
    client.post("/v1/chat", json={"message": "list invoices"},
                headers={"Authorization": "Bearer abc", "X-User-Role": "accountant"})
    assert seen["ctx"].token == "abc" and seen["ctx"].role == "accountant"
