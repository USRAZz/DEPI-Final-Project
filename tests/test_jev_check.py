"""python -m ai_core.jev_check: settings, catalogue, key and test call. Offline: OpenRouter is a mock transport."""
import httpx
import pytest

from ai_core import jev_check

CATALOGUE = {"data": [{"id": "typesafe/jev-router"}, {"id": "openai/gpt-4o-mini"}]}
KEY = {"data": {"label": "securefin-dev", "usage": 0.42, "limit": None, "is_free_tier": False}}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setattr(jev_check, "load_dotenv", lambda: None)  # never read the real .env in tests
    for k in ("LLM_ROUTING", "JEV_MODELS", "JEV_EXCLUDED_MODELS", "JEV_COST_TIER", "JEV_FALLBACK_MODEL", "AGENT_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LLM_ROUTING", "jev")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")


def client(chat_status=200, catalogue=CATALOGUE, key_status=200):
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json=catalogue)
        if req.url.path.endswith("/key"):
            return httpx.Response(key_status, json=KEY)
        if chat_status == 200:
            return httpx.Response(200, json={"model": "google/gemini-2.5-flash", "choices": []})
        return httpx.Response(chat_status, json={"error": {"message": "no access"}})

    c = httpx.Client(transport=httpx.MockTransport(handler))
    c.seen = seen
    return c


def test_without_call_nothing_is_sent_to_the_chat_endpoint(capsys):
    c = client()
    assert jev_check.check(False, c) == 0
    assert not any(r.url.path.endswith("/chat/completions") for r in c.seen)
    out = capsys.readouterr().out
    assert "typesafe/jev-router: listed" in out and "agent" in out and "cost tier medium" in out
    assert "sk-or-test" not in out  # the key itself is never printed


def test_a_working_router_reports_the_model_it_picked(capsys):
    c = client()
    assert jev_check.check(True, c) == 0
    [chat] = [r for r in c.seen if r.url.path.endswith("/chat/completions")]
    assert b'"typesafe/jev-router"' in chat.content and chat.headers["X-OpenRouter-Metadata"] == "enabled"
    assert "It picked: google/gemini-2.5-flash" in capsys.readouterr().out


@pytest.mark.parametrize(("status", "words"), [(404, "workspaces that allow it"), (503, "temporarily unavailable"),
                                               (402, "no credit")])
def test_refusals_say_what_to_do(status, words, capsys):
    assert jev_check.check(True, client(chat_status=status)) == 1
    assert words in capsys.readouterr().out


def test_a_bad_key_stops_before_the_call(capsys):
    c = client(key_status=401)
    assert jev_check.check(True, c) == 1
    assert "key is wrong or revoked" in capsys.readouterr().out
    assert not any(r.url.path.endswith("/chat/completions") for r in c.seen)


def test_missing_from_the_catalogue_is_reported(capsys):
    assert jev_check.check(False, client(catalogue={"data": []})) == 1
    assert "NOT listed" in capsys.readouterr().out


def test_a_fixed_model_for_a_role_is_shown(monkeypatch, capsys):
    monkeypatch.setenv("AGENT_MODEL", "openai/gpt-4o")
    jev_check.check(False, client())
    assert "fixed model openai/gpt-4o (AGENT_MODEL wins over Jev)" in capsys.readouterr().out
