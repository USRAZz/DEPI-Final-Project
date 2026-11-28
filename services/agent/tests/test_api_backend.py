"""BACKEND=api: the tools call services/api's real endpoints with the user's identity. Offline: mock transport."""
import app.main as main
import httpx
import pytest
from app.tools import ApiBackend, Context, ToolRegistry
from fastapi.testclient import TestClient

INVOICES = [{"id": 412, "vendor_id": 1, "vendor_name": "Nile Paper", "invoice_number": "INV-2026-0412",
             "invoice_date": "2026-10-28", "total_amount": 15400.0, "currency": "EGP", "status": "FLAGGED",
             "category": "materials", "extraction_issues": [], "duplicate_of": 371}]
RISK = {"invoice_id": 412, "scored": True, "score": 72, "level": "high", "rule_hits": ["DUPLICATE_INVOICE"]}


@pytest.fixture
def api():
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        if req.url.path == "/invoices":
            return httpx.Response(200, json=INVOICES)
        if req.url.path == "/transactions":
            return httpx.Response(200, json=[])
        if req.url.path == "/invoices/412/risk":
            return httpx.Response(200, json=RISK)
        return httpx.Response(404, json={"detail": "not found"})

    backend = ApiBackend("http://api", transport=httpx.MockTransport(handler))
    backend.seen = seen
    return backend


def test_tools_call_the_real_paths_with_the_users_identity(api):
    ctx = Context(user_id="2", role="approver")
    reg = ToolRegistry(api)
    assert reg.call("get_invoices", {"status": "FLAGGED"}, ctx) == INVOICES
    reg.call("get_transactions", {"date_from": "2026-10-01"}, ctx)
    assert reg.call("get_risk_score", {"invoice_id": 412}, ctx)["level"] == "high"
    paths = [r.url.path for r in api.seen]
    assert paths == ["/invoices", "/transactions", "/invoices/412/risk"]
    assert all(r.headers["X-User-Id"] == "2" for r in api.seen)
    assert api.seen[0].url.params["status"] == "FLAGGED" and api.seen[0].url.params["limit"] == "50"
    assert "date_to" not in api.seen[1].url.params  # empty filters are not sent


def test_the_limit_is_kept_inside_the_apis_maximum(api):
    api.get_invoices(Context(user_id="2"), {"limit": 1000})
    assert api.seen[0].url.params["limit"] == "200"


def test_the_demo_user_is_never_sent_as_an_identity(api):
    api.get_invoices(Context(), {})
    assert "X-User-Id" not in api.seen[0].headers


def test_alerts_work_on_api_data(api):
    from app.alerts import build_alerts
    reg = ToolRegistry(api)
    ctx = Context(user_id="2")
    reg.call("get_invoices", {}, ctx)
    [alert] = build_alerts(reg.calls, api, ctx, "en")
    assert alert.invoice_id == 412 and alert.level.value == "high" and alert.reasons[0].code == "DUPLICATE_INVOICE"


def test_an_unscored_invoice_from_the_api_is_not_an_alert(api, monkeypatch):
    from app.alerts import build_alerts
    clean = [{**INVOICES[0], "status": "VALIDATED", "duplicate_of": None}]
    calls = [("get_invoices", {}, clean), ("get_risk_score", {"invoice_id": 412},
                                            {"scored": False, "score": None, "level": None, "rule_hits": []})]
    assert build_alerts(calls, api, Context(), "en") == []


def test_agent_needs_the_service_token_when_one_is_configured(monkeypatch):
    monkeypatch.setenv("AGENT_SERVICE_TOKEN", "agent-secret")
    client = TestClient(main.app)
    for path, body in [("/v1/chat", {"message": "hi"}), ("/v1/reports", {"request": "x"}),
                       ("/v1/explain", {"risk": {"score": 0, "level": "low"}})]:
        assert client.post(path, json=body).status_code == 401
        assert client.post(path, json=body, headers={"X-Service-Token": "wrong"}).status_code == 401
    assert client.get("/health").status_code == 200
