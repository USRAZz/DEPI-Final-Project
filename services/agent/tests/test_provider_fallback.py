"""LLM_FALLBACK_PROVIDERS: when one provider's quota or credit runs out (429/402) the next one answers.
Offline: the HTTP calls are fakes; no key is used."""
import httpx
import openai
import pytest

from ai_core import llm as llm_mod


@pytest.fixture
def env(monkeypatch):
    for k in ("LLM_ROUTING", "AGENT_MODEL", "AGENT_PROVIDER", "QUOTA_RETRY_SECONDS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-or")
    monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/free")
    monkeypatch.setenv("OPENAI_API_KEY", "test-oa")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDERS", "openrouter,openai")
    monkeypatch.setattr(llm_mod, "_quota_until", {})
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)  # no real waiting in tests
    return monkeypatch


def _error(code):
    resp = httpx.Response(code, request=httpx.Request("POST", "https://example.test/chat/completions"))
    cls = openai.RateLimitError if code == 429 else openai.APIStatusError
    return cls("quota", response=resp, body=None)


class _Resp:
    def __init__(self, model):
        self.model = model
        self.choices = [type("C", (), {"message": type("M", (), {"content": "ok"})(), "finish_reason": "stop"})()]
        self.usage = None


def wire(llm, answers: dict):
    """answers: provider -> HTTP status to fail with, or None to answer."""
    sent = []
    for client in [llm, *llm.fallbacks]:
        def create(_p=client.provider, **kw):
            sent.append(_p)
            if answers.get(_p):
                raise _error(answers[_p])
            return _Resp(kw["model"])
        client.client.chat.completions.create = create
    return sent


def test_the_chain_is_built_from_the_approved_providers(env):
    llm = llm_mod.get_llm("agent")
    assert llm.provider == "openrouter" and [f.provider for f in llm.fallbacks] == ["openai"]


@pytest.mark.parametrize("code", [429, 402])
def test_used_up_quota_moves_to_the_next_provider(env, code):
    llm = llm_mod.get_llm("agent")
    sent = wire(llm, {"openrouter": code})
    assert llm.chat([{"role": "user", "content": "hi"}]) == "ok"
    assert sent[-1] == "openai" and dict(llm.usage.models) == {"gpt-4o-mini": 1}


def test_a_used_up_provider_is_skipped_for_a_while(env):
    llm = llm_mod.get_llm("agent")
    sent = wire(llm, {"openrouter": 429})
    llm.chat([{"role": "user", "content": "one"}])
    n = len(sent)
    llm.chat([{"role": "user", "content": "two"}])
    assert sent[n:] == ["openai"]  # straight to the fallback, no waiting on the used-up one


def test_other_errors_are_not_hidden(env):
    llm = llm_mod.get_llm("agent")
    wire(llm, {"openrouter": 401})
    with pytest.raises(openai.APIStatusError):
        llm.chat([{"role": "user", "content": "hi"}])


def test_when_every_provider_is_used_up_the_error_is_raised(env):
    llm = llm_mod.get_llm("agent")
    wire(llm, {"openrouter": 429, "openai": 402})
    with pytest.raises(openai.APIStatusError):
        llm.chat([{"role": "user", "content": "hi"}])


def test_fallback_messages_are_masked_too(env):
    llm = llm_mod.get_llm("agent")
    seen = []
    llm.client.chat.completions.create = lambda **kw: (_ for _ in ()).throw(_error(429))

    def openai_create(**kw):
        seen.append(kw["messages"][0]["content"])
        return _Resp(kw["model"])

    llm.fallbacks[0].client.chat.completions.create = openai_create
    llm.chat([{"role": "user", "content": "pay EG380019000500000000263180002"}])
    assert seen == ["pay [IBAN]"]


def test_a_provider_without_key_is_skipped_and_an_unapproved_one_refused(env):
    env.delenv("OPENAI_API_KEY")
    assert llm_mod.get_llm("agent").fallbacks == []
    env.setenv("LLM_FALLBACK_PROVIDERS", "ollama")
    with pytest.raises(ValueError, match="unknown provider"):
        llm_mod.get_llm("agent")


# ---- all free: OpenRouter, then Groq (two models, each with its own limit), then OpenAI ---------------------------

@pytest.fixture
def free(env):
    env.setenv("GROQ_API_KEY", "test-gq")
    env.setenv("GROQ_MODEL", "openai/gpt-oss-20b")
    env.setenv("LLM_FALLBACK_PROVIDERS", "openrouter,groq,groq:llama-3.1-8b-instant,openai")
    return env


def test_the_free_order_with_two_groq_models(free):
    llm = llm_mod.get_llm("agent")
    assert [(f.provider, f.model) for f in llm.fallbacks] == [
        ("groq", "openai/gpt-oss-20b"), ("groq", "llama-3.1-8b-instant"), ("openai", "gpt-4o-mini")]


def test_a_model_entry_keeps_colons_in_openrouter_ids(free):
    free.setenv("LLM_FALLBACK_PROVIDERS", "openrouter:meta-llama/llama-3.3-70b-instruct:free")
    [fb] = llm_mod.get_llm("agent").fallbacks
    assert (fb.provider, fb.model) == ("openrouter", "meta-llama/llama-3.3-70b-instruct:free")


def test_each_groq_model_has_its_own_quota(free):
    llm = llm_mod.get_llm("agent")
    sent = []
    for client in [llm, *llm.fallbacks]:
        def create(_c=client, **kw):
            sent.append(_c.quota_key)
            if _c.quota_key in ("openrouter:openrouter/free", "groq:openai/gpt-oss-20b"):
                raise _error(429)
            return _Resp(kw["model"])
        client.client.chat.completions.create = create
    assert llm.chat([{"role": "user", "content": "hi"}]) == "ok"
    assert sent[-1] == "groq:llama-3.1-8b-instant" and dict(llm.usage.models) == {"llama-3.1-8b-instant": 1}
    assert set(llm_mod.quota_status()) == {"openrouter:openrouter/free", "groq:openai/gpt-oss-20b"}


# ---- waiting exactly until the free quota renews ----------------------------------------------------------------

@pytest.mark.parametrize(("headers", "low", "high"), [
    ({"retry-after": "42"}, 42, 42),                                      # the provider's answer for this refusal
    ({"x-ratelimit-reset": str(int((llm_mod.time.time() + 3600) * 1000))}, 3500, 3600),  # OpenRouter: epoch ms
    ({"x-ratelimit-reset-requests": "2h3m4.5s", "x-ratelimit-reset-tokens": "7.66s"}, 7384, 7385),  # Groq: latest
    ({"retry-after": "8", "x-ratelimit-reset-requests": "2h"}, 8, 8),     # retry-after wins
    ({}, None, None),
])
def test_reset_time_is_read_from_the_headers(headers, low, high):
    got = llm_mod.reset_seconds(headers)
    assert got is None if low is None else low <= got <= high


def test_a_used_up_model_is_skipped_until_its_announced_reset(env):
    llm = llm_mod.get_llm("agent")
    resp = httpx.Response(429, headers={"retry-after": "120"},
                          request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"))
    llm.client.chat.completions.create = lambda **kw: (_ for _ in ()).throw(
        openai.RateLimitError("daily", response=resp, body=None))
    llm.fallbacks[0].client.chat.completions.create = lambda **kw: _Resp(kw["model"])
    llm.chat([{"role": "user", "content": "hi"}])
    assert 115 <= llm_mod.quota_status()["openrouter:openrouter/free"] <= 120


def test_after_the_reset_the_main_provider_is_used_again(env):
    llm = llm_mod.get_llm("agent")
    wire(llm, {"openrouter": 429})
    llm.chat([{"role": "user", "content": "one"}])
    env.setattr(llm_mod, "_quota_until", {})  # the day changed: the free quota is back
    sent = wire(llm, {})
    llm.chat([{"role": "user", "content": "two"}])
    assert sent == ["openrouter"]


def test_no_chain_keeps_the_old_behaviour(env):
    env.delenv("LLM_FALLBACK_PROVIDERS")
    llm = llm_mod.get_llm("agent")
    sent = wire(llm, {"openrouter": 429})
    with pytest.raises(openai.RateLimitError):
        llm.chat([{"role": "user", "content": "hi"}])
    assert len(sent) == 4  # the usual four tries with waits


# ---- python -m ai_core.llm_check ------------------------------------------------------------------------------

def test_llm_check_reports_each_provider(env, monkeypatch, capsys):
    from ai_core import llm_check
    monkeypatch.setattr(llm_check, "load_dotenv", lambda: None)

    def handler(req: httpx.Request):
        if "openrouter" in str(req.url):
            return httpx.Response(429, headers={"retry-after": "3600"}, json={"error": {"message": "per-day"}})
        return httpx.Response(200, json={"model": "gpt-4o-mini-2024-07-18"})

    code = llm_check.check(True, httpx.Client(transport=httpx.MockTransport(handler)))
    out = capsys.readouterr().out
    assert code == 0 and "openrouter:openrouter/free -> openai:gpt-4o-mini" in out
    assert "free quota used up, comes back by itself in 1h 0m" in out and "OK, answered by gpt-4o-mini" in out
    assert "test-or" not in out and "test-oa" not in out  # keys never printed
