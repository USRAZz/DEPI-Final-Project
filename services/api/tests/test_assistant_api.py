"""The assistant's read endpoints, chat/reports through the agent, and two payment fixes (double execute, account of
another vendor). Every store test runs on the in-memory store and on SQLite, like test_api.py."""
import httpx
import pytest
from app import assistant
from app.main import create_app
from app.store import (
    ACC_NILE,
    INV_0371,
    INV_0412,
    KARIM,
    MONA,
    OUTSIDER,
    PR_187,
    PR_189,
    VIEWER,
    PaymentStateConflict,
    seeded_store,
)
from fastapi.testclient import TestClient
from securefin_contracts import InvoiceStatus
from tests.fakes import FakeGateway, sql_store_with_sample_data


@pytest.fixture(params=["memory", "sqlite"])
def store(request):
    return seeded_store() if request.param == "memory" else sql_store_with_sample_data(None)


@pytest.fixture
def client(store):
    return TestClient(create_app(store=store, gateway=FakeGateway(store)))


def as_user(user_id):
    return {"X-User-Id": str(user_id)}


# ---- GET /invoices ------------------------------------------------------------------------------------------------

def test_invoices_list_has_the_tool_shape_newest_first(client):
    rows = client.get("/invoices", headers=as_user(KARIM)).json()
    assert {r["id"] for r in rows} == {INV_0371, INV_0412, 415, 416, 417}
    flagged = next(r for r in rows if r["id"] == INV_0412)
    assert flagged == {**flagged, "vendor_name": "Nile Paper", "invoice_number": "INV-2026-0412", "status": "FLAGGED",
                       "total_amount": 15400.0, "invoice_date": "2026-10-28", "duplicate_of": INV_0371}
    assert [r["invoice_date"] for r in rows] == sorted((r["invoice_date"] for r in rows), reverse=True)


def test_invoices_without_fields_take_the_amount_of_their_payment_request(client):
    row = next(r for r in client.get("/invoices", headers=as_user(KARIM)).json() if r["id"] == 415)
    assert row["total_amount"] == 8750.0 and row["vendor_name"] == "Egyptian Packaging"


@pytest.mark.parametrize(("query", "ids"), [
    ({"status": "flagged"}, {INV_0412}),
    ({"vendor_name": "nile"}, {INV_0371, INV_0412}),
    ({"date_from": "2026-10-28", "date_to": "2026-10-31"}, {INV_0412}),
    ({"limit": 2}, None),
])
def test_invoice_filters(client, query, ids):
    rows = client.get("/invoices", params=query, headers=as_user(KARIM)).json()
    assert ({r["id"] for r in rows} == ids) if ids is not None else len(rows) == 2


def test_another_company_sees_none_of_these_invoices(client):
    assert client.get("/invoices", headers=as_user(OUTSIDER)).json() == []
    assert client.get(f"/invoices/{INV_0412}/risk", headers=as_user(OUTSIDER)).status_code == 404


def test_the_read_endpoints_need_sign_in(client):
    for path in ("/invoices", "/transactions", f"/invoices/{INV_0412}/risk"):
        assert client.get(path).status_code == 401


# ---- GET /invoices/{id}/risk, GET /transactions --------------------------------------------------------------------

def test_invoice_risk_is_the_score_of_its_payment_request(client):
    body = client.get(f"/invoices/{INV_0412}/risk", headers=as_user(VIEWER)).json()
    assert body["scored"] and body["payment_request_id"] == PR_187 and body["level"] == "high"
    assert "DUPLICATE_INVOICE" in body["rule_hits"]


def test_an_unscored_invoice_says_so(client):
    body = client.get(f"/invoices/{INV_0371}/risk", headers=as_user(KARIM)).json()
    assert body == {"invoice_id": INV_0371, "scored": False, "score": None, "level": None, "rule_hits": []}


def test_transactions_list_paid_requests_only(client, store):
    assert client.get("/transactions", headers=as_user(KARIM)).json() == []
    store.set_request_status(PR_189, InvoiceStatus.PAID_SIMULATED)
    [row] = client.get("/transactions", headers=as_user(KARIM)).json()
    assert row["payment_request_id"] == PR_189 and row["amount"] == 2300.0 and row["vendor_name"] == "Cairo Net"
    assert client.get("/transactions", params={"date_to": "2000-01-01"}, headers=as_user(KARIM)).json() == []


# ---- double execute -------------------------------------------------------------------------------------------------

def test_a_second_mark_paid_is_refused_by_the_store(store):
    store.mark_paid(PR_189)
    with pytest.raises(PaymentStateConflict):
        store.mark_paid(PR_189)
    assert store.times_paid(store.payment_request_by_id(PR_189).bank_account_id) == 23  # 22 + one payment only


def test_a_concurrent_execute_that_loses_the_race_gets_409_and_pays_nothing(client, store, monkeypatch):
    """Both requests passed the route's checks; the store's locked re-check stops the second one."""
    for approver in (MONA, KARIM):
        client.post(f"/payment-requests/{PR_189}/approvals", json={"approved": True}, headers=as_user(approver))

    def already_paid(request_id):
        raise PaymentStateConflict(request_id)

    monkeypatch.setattr(store, "mark_paid", already_paid)
    r = client.post(f"/payment-requests/{PR_189}/execute", headers=as_user(KARIM))
    assert r.status_code == 409 and "nothing was paid" in r.json()["detail"][0]


# ---- account of another vendor -----------------------------------------------------------------------------------

def test_a_verified_account_of_another_vendor_is_refused():
    store = seeded_store()
    store.payment_requests[PR_189] = store.payment_requests[PR_189].model_copy(update={"bank_account_id": ACC_NILE})
    client = TestClient(create_app(store=store, gateway=FakeGateway(store)))
    r = client.post(f"/payment-requests/{PR_189}/approvals", json={"approved": True}, headers=as_user(MONA))
    assert r.status_code == 409 and "does not belong to this vendor" in r.json()["detail"]


# ---- POST /chat and /reports go to the agent with the session's identity ---------------------------------------------

@pytest.fixture
def agent(monkeypatch):
    sent = []

    def fake_post(url, json, headers, timeout):
        sent.append({"url": url, "json": json, "headers": headers})
        if url.endswith("/v1/chat"):
            return httpx.Response(200, json={"answer": "Invoice 412 is a duplicate.", "proposed_actions": [],
                                             "alerts": [], "sources": ["get_invoices"]})
        return httpx.Response(200, json={"title": "October", "language": "en", "date_from": "2026-10-01",
                                         "date_to": "2026-10-31", "summary": "s", "rounds": 1, "quality": "passed"})

    monkeypatch.setattr(assistant.httpx, "post", fake_post)
    monkeypatch.setenv("AGENT_URL", "http://agent-test")
    return sent


def test_chat_goes_to_the_agent_with_the_users_id_and_role(client, agent):
    r = client.post("/chat", json={"message": "flagged?"}, headers={**as_user(MONA), "X-User-Role": "admin"})
    assert r.status_code == 200 and r.json()["sources"] == ["get_invoices"]
    [call] = agent
    assert call["url"] == "http://agent-test/v1/chat"
    assert call["headers"]["X-User-Id"] == str(MONA) and call["headers"]["X-User-Role"] == "approver"  # the session's


def test_reports_go_to_the_agent(client, agent):
    r = client.post("/reports", json={"request": "October report"}, headers=as_user(KARIM))
    assert r.status_code == 200 and r.json()["quality"] == "passed" and agent[0]["url"].endswith("/v1/reports")


def test_chat_needs_sign_in_and_never_calls_the_agent_without_it(client, agent):
    assert client.post("/chat", json={"message": "hi"}).status_code == 401 and agent == []


def test_agent_down_is_503(client, monkeypatch):
    def down(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(assistant.httpx, "post", down)
    r = client.post("/chat", json={"message": "hi"}, headers=as_user(KARIM))
    assert r.status_code == 503 and r.json()["detail"] == "assistant unavailable"


def test_agent_service_token_is_sent_when_configured(client, agent, monkeypatch):
    monkeypatch.setenv("AGENT_SERVICE_TOKEN", "agent-secret")
    client.post("/chat", json={"message": "hi"}, headers=as_user(KARIM))
    assert agent[0]["headers"]["X-Service-Token"] == "agent-secret"
