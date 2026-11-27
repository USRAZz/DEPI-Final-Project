import app.main as main
import pytest
from app.security import load_service_token, token_matches
from fastapi.testclient import TestClient

TOKEN = "t" * 40
client = TestClient(main.app)

AUTH_BODY = {"user_id": 7, "role": "viewer", "company_id": 1, "request_id": "r1",
             "action": {"tool": "get_invoices", "params": {}}}
APPROVAL_BODY = {"payment_request_id": 1, "approver_id": 10, "approve": True, "approver_role": "approver",
                 "company_id": 1}
EXECUTE_BODY = {"payment_request_id": 1, "requested_by": 7, "company_id": 1}
ROUTES = [("/v1/authorize", AUTH_BODY), ("/v1/approvals/1", APPROVAL_BODY), ("/v1/execute-check", EXECUTE_BODY)]


@pytest.fixture(autouse=True)
def real_auth(monkeypatch):
    main.app.dependency_overrides.pop(main.require_service_token, None)
    monkeypatch.setenv("GATEWAY_SERVICE_TOKEN", TOKEN)


@pytest.mark.parametrize(("path", "body"), ROUTES)
def test_no_token_is_401(path, body):
    assert client.post(path, json=body).status_code == 401


@pytest.mark.parametrize(("path", "body"), ROUTES)
def test_wrong_token_is_401(path, body):
    assert client.post(path, json=body, headers={"X-Service-Token": "x" * 40}).status_code == 401


@pytest.mark.parametrize(("path", "body"), ROUTES)
@pytest.mark.parametrize("configured", [None, "short"])
def test_token_not_configured_refuses_everything(monkeypatch, path, body, configured):
    if configured is None:
        monkeypatch.delenv("GATEWAY_SERVICE_TOKEN")
    else:
        monkeypatch.setenv("GATEWAY_SERVICE_TOKEN", configured)
    # even sending the "right" value must not work when the gateway is not configured
    r = client.post(path, json=body, headers={"X-Service-Token": configured or ""})
    assert r.status_code == 503


def test_right_token_reaches_the_endpoint():
    r = client.post("/v1/authorize", json=AUTH_BODY, headers={"X-Service-Token": TOKEN})
    assert r.status_code == 200 and r.json()["decision"] == "ALLOW"


def test_health_needs_no_token():
    assert client.get("/health").json()["status"] == "ok"


def test_token_helpers():
    assert token_matches(TOKEN, TOKEN) and not token_matches(None, TOKEN) and not token_matches("x", TOKEN)
    assert load_service_token() == TOKEN
