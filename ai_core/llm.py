"""LLM client for the OpenAI chat-completions API. The model comes from .env.
Every message is masked with ai_core.privacy before it leaves the process.

Model choice per request (Jev Router): with LLM_ROUTING=jev (or <ROLE>_ROUTING=jev) the call goes to OpenRouter's
`typesafe/jev-router`, which reads the request and picks a model from its pool: the cheapest one good enough for the
task. Each role sends its own cost tier (a cheap tier for routing and labels, a high one for the report evaluator),
and the team can narrow the pool with JEV_MODELS / JEV_EXCLUDED_MODELS. The model that actually answered is recorded
in Usage.models. If the router is unavailable (404/503) the call is retried once on JEV_FALLBACK_MODEL.
"""
import json
import logging
import os
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass, field

from dotenv import load_dotenv
from openai import APIStatusError, BadRequestError, NotFoundError, OpenAI, RateLimitError

from .privacy import mask_messages
from .tls import use_system_certs

load_dotenv()
use_system_certs()  # USE_SYSTEM_CERTS=true: HTTPS through an inspecting proxy / antivirus (ai_core/tls.py)


# Decision (SecureFin plan 1.2, updated 28/11 by Yousra): OpenAI, OpenRouter and Groq, all used on their free tiers.
# Every message is masked (ai_core.privacy) before it is sent, whichever provider answers.
PROVIDERS = {
    "openai": {
        "base_url": None,
        "key_env": "OPENAI_API_KEY",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
    },
}

JEV_MODEL = "typesafe/jev-router"
# Default Jev cost tier per role: cheap where a small model is enough, high where the answer is checked for others.
JEV_TIERS = {
    "router": "low", "categorizer": "low", "explainer": "low",
    "extractor": "medium", "agent": "medium",
    "report_orchestrator": "low", "report_worker": "low", "report_writer": "medium", "report_evaluator": "high",
}
_JEV_UNAVAILABLE = {404, 503}
_JEV_HINTS = {404: "no access to the router for this key/workspace, or no model left after JEV_MODELS / "
                   "JEV_EXCLUDED_MODELS / account restrictions",
              503: "the router is temporarily unavailable"}
_jev_down_until = 0.0  # after a 404/503, calls go straight to the fallback model until this time (monotonic)
_quota_until: dict[str, float] = {}  # "provider:model" -> skip it until this time (its free quota ran out)
log = logging.getLogger(__name__)
_DURATION = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")


def _is_quota(e: Exception) -> bool:
    """429 = rate limit or daily quota of the free tier; 402 = no credit left. Not: a wrong key, a bad request."""
    return isinstance(e, APIStatusError) and e.status_code in (402, 429)


def _duration(text: str) -> float | None:
    """Groq style '2m59.56s', '7.66s', '1h2m', '250ms' -> seconds."""
    parts = _DURATION.findall(text or "")
    if not parts or "".join(n + u for n, u in parts) != text.strip():
        return None
    scale = {"h": 3600, "m": 60, "s": 1, "ms": 0.001}
    return sum(float(n) * scale[u] for n, u in parts)


def reset_seconds(headers) -> float | None:
    """When the provider says its quota comes back, in seconds from now; None when it does not say.
    retry-after (seconds) is the provider's answer for THIS refusal and wins. Otherwise OpenRouter x-ratelimit-reset
    (epoch in ms) or Groq x-ratelimit-reset-requests/-tokens ('2m59.56s'), the latest of them."""
    first = (headers.get("retry-after") or "").strip()
    if first:
        try:
            if float(first) > 0:
                return float(first)
        except ValueError:
            pass
    found = []
    for name in ("x-ratelimit-reset", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
        value = (headers.get(name) or "").strip()
        if not value:
            continue
        try:
            number = float(value)
        except ValueError:
            if (d := _duration(value)) is not None:
                found.append(d)
            continue
        if number > 1e12:      # epoch milliseconds (OpenRouter)
            found.append(number / 1000 - time.time())
        elif number > 1e9:     # epoch seconds
            found.append(number - time.time())
        else:                  # plain seconds
            found.append(number)
    found = [s for s in found if s > 0]
    return max(found) if found else None


def _mark_used_up(key: str, e: APIStatusError) -> None:
    """Skip this provider/model until its quota is back: the time it announced, else QUOTA_RETRY_SECONDS.
    Free daily limits renew by themselves, so after that time it is simply tried again."""
    announced = reset_seconds(getattr(getattr(e, "response", None), "headers", {}) or {})
    seconds = announced if announced is not None else float(os.getenv("QUOTA_RETRY_SECONDS", "900"))
    seconds = min(max(seconds, 5.0), 86400.0)
    _quota_until[key] = time.monotonic() + seconds
    log.warning("%s answered %s (free quota used up); the next one in LLM_FALLBACK_PROVIDERS answers for %s "
                "(%s). Check with `python -m ai_core.llm_check`.", key, e.status_code, _human(seconds),
                "as the provider announced" if announced is not None else "QUOTA_RETRY_SECONDS")


def _human(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    return f"{h}h {rem // 60}m" if h else f"{rem // 60}m {rem % 60}s"


def quota_status() -> dict[str, float]:
    """provider:model -> seconds until it is tried again (only the ones currently skipped)."""
    now = time.monotonic()
    return {k: round(v - now) for k, v in _quota_until.items() if v > now}



class BudgetExceeded(Exception):
    pass


class StructuredOutputError(Exception):
    pass


@dataclass
class Budget:
    """Hard limits for one request (tokens and seconds)."""
    max_tokens: int = 20000
    max_seconds: float = 90.0
    tokens: int = 0
    started: float = field(default_factory=time.perf_counter)

    def check(self):
        if self.tokens >= self.max_tokens:
            raise BudgetExceeded(f"token budget reached ({self.max_tokens})")
        if time.perf_counter() - self.started >= self.max_seconds:
            raise BudgetExceeded(f"time budget reached ({self.max_seconds}s)")


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0
    models: Counter = field(default_factory=Counter)  # model that actually answered -> calls (Jev picks per call)

    def as_dict(self):
        d = asdict(self)
        d["models"] = dict(self.models)
        return d


def _extract_json(text: str) -> dict:
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        raise ValueError("no JSON object found in the reply")
    return json.loads(text[s:e + 1])  # also strips ```json fences


class LLM:
    def __init__(self, provider: str, model: str, *, timeout: float = 60.0, max_tokens: int = 2000,
                 temperature: float | None = 0.0, extra_body: dict | None = None, fallback_model: str | None = None):
        cfg = PROVIDERS.get(provider)
        if cfg is None:
            raise ValueError(f"unknown provider '{provider}'. Use one of {list(PROVIDERS)}")
        key = os.getenv(cfg["key_env"])
        if not key:
            raise RuntimeError(f"missing {cfg['key_env']} in .env")
        self.provider, self.model = provider, model
        self.quota_key = f"{provider}:{model}"  # free limits are per provider (and per model on Groq)
        self.extra_body, self.fallback_model = extra_body, fallback_model
        self.client = OpenAI(api_key=key, base_url=cfg["base_url"], timeout=timeout)
        # request options; auto-corrected below when a provider/model rejects one of them
        self.opts = {"temperature": temperature, "max_tokens": max_tokens, "tokens_param": "max_tokens", "json_mode": True}
        self.usage = Usage()
        # Other providers (LLM_FALLBACK_PROVIDERS) tried in order when this one's quota or credit runs out.
        self.fallbacks: list[LLM] = []

    def _fallback_kw(self, kw: dict) -> dict:
        kw = {**kw, "model": self.fallback_model}
        kw.pop("extra_body", None)
        return kw

    def _create(self, kw: dict):
        global _jev_down_until
        if kw.get("model") == JEV_MODEL and self.fallback_model and time.monotonic() < _jev_down_until:
            return self._create_with_retries(self._fallback_kw(kw))  # Jev failed recently: do not wait for it again
        try:
            return self._create_with_retries(kw)
        except APIStatusError as e:
            # Jev Router down (503) or no eligible model / no access (404): one retry on a fixed model, if set.
            if kw.get("model") != JEV_MODEL or not self.fallback_model or e.status_code not in _JEV_UNAVAILABLE:
                raise
            _jev_down_until = time.monotonic() + float(os.getenv("JEV_RETRY_SECONDS", "300"))
            log.warning("Jev Router answered %s (%s); using %s for the next %ss. Run `python -m ai_core.jev_check` "
                        "to see why.", e.status_code, _JEV_HINTS.get(e.status_code, ""), self.fallback_model,
                        os.getenv("JEV_RETRY_SECONDS", "300"))
            return self._create_with_retries(self._fallback_kw(kw))

    def _create_with_retries(self, kw: dict):
        # Free tiers rate-limit often: wait, then retry. With a fallback provider waiting long is pointless
        # (a daily quota does not come back in 46 s), so retry once and move on.
        for wait in ((0, 2) if self.fallbacks else (0, 4, 12, 30)):
            time.sleep(wait)
            try:
                return self._create_once(kw)
            except RateLimitError as e:
                err = e
        raise err

    
    def _create_once(self, kw: dict):
        for _ in range(4):
            try:
                return self.client.chat.completions.create(**kw)
            except (BadRequestError, NotFoundError) as e:
                m = str(e).lower()
                if "max_tokens" in m or "max_completion_tokens" in m:
                    if "max_tokens" in kw:
                        kw["max_completion_tokens"] = kw.pop("max_tokens")
                        self.opts["tokens_param"] = "max_completion_tokens"
                    elif "max_completion_tokens" in kw:
                        kw["max_tokens"] = kw.pop("max_completion_tokens")
                        self.opts["tokens_param"] = "max_tokens"
                    else:
                        raise
                elif "temperature" in m and "temperature" in kw:
                    kw.pop("temperature")
                    self.opts["temperature"] = None
                elif ("response_format" in m or isinstance(e, NotFoundError)) and "response_format" in kw:
                    kw.pop("response_format")
                    self.opts["json_mode"] = False
                else:
                    raise
        raise RuntimeError("the provider keeps rejecting the request parameters")

    def chat(self, messages: list[dict], *, json_mode: bool = False, budget: Budget | None = None) -> str:
        """One call. When this provider's quota or credit is used up (429/402) and fallbacks are configured, the
        same masked messages go to the next provider; the used-up one is skipped for QUOTA_RETRY_SECONDS."""
        if budget:
            budget.check()
        if self.fallbacks and time.monotonic() < _quota_until.get(self.quota_key, 0.0):
            return self._chat_fallback(messages, json_mode, budget, None)
        try:
            return self._chat_here(messages, json_mode=json_mode, budget=budget)
        except APIStatusError as e:
            if not self.fallbacks or not _is_quota(e):
                raise
            _mark_used_up(self.quota_key, e)
            return self._chat_fallback(messages, json_mode, budget, e)

    def _chat_fallback(self, messages, json_mode, budget, error):
        for fb in self.fallbacks:
            if time.monotonic() < _quota_until.get(fb.quota_key, 0.0):
                continue
            before = Counter(fb.usage.models)
            try:
                text = fb._chat_here(messages, json_mode=json_mode, budget=budget)
            except APIStatusError as e:
                if not _is_quota(e):
                    raise
                _mark_used_up(fb.quota_key, e)
                error = e
                continue
            self.usage.models.update(fb.usage.models - before)  # the model that answered, whoever served it
            self.usage.calls += 1
            return text
        if error is not None:
            raise error
        raise RuntimeError("every LLM provider is out of quota right now; try again later")

    def _chat_here(self, messages: list[dict], *, json_mode: bool = False, budget: Budget | None = None) -> str:
        kw = {"model": self.model, "messages": mask_messages(messages), self.opts["tokens_param"]: self.opts["max_tokens"]}
        if self.opts["temperature"] is not None:
            kw["temperature"] = self.opts["temperature"]
        if json_mode and self.opts["json_mode"]:
            kw["response_format"] = {"type": "json_object"}
        if self.extra_body:
            kw["extra_body"] = self.extra_body
        t0 = time.perf_counter()
        r = self._create(kw)
        self.usage.models[getattr(r, "model", None) or kw["model"]] += 1
        text = r.choices[0].message.content or ""
        if not text.strip() and r.choices[0].finish_reason == "length":
            raise RuntimeError("empty reply: the model ran out of tokens (thinking models?). Raise LLM_MAX_TOKENS")
        u = getattr(r, "usage", None)
        pt, ct = (getattr(u, "prompt_tokens", 0) or 0), (getattr(u, "completion_tokens", 0) or 0)
        self.usage.calls += 1
        self.usage.prompt_tokens += pt
        self.usage.completion_tokens += ct
        self.usage.seconds += time.perf_counter() - t0
        if budget:
            budget.tokens += pt + ct
        return text

    def structured(self, messages: list[dict], schema, *, retries: int = 1, budget: Budget | None = None):
        """Ask for JSON, validate it against a Pydantic model, and retry once with the error message."""
        msgs, err = list(messages), None
        for _ in range(retries + 1):
            raw = self.chat(msgs, json_mode=True, budget=budget)
            try:
                return schema.model_validate(_extract_json(raw))
            except ValueError as e:  # JSON errors and Pydantic ValidationError both inherit ValueError
                err = e
                msgs += [{"role": "assistant", "content": raw},
                         {"role": "user", "content": f"That reply was invalid: {str(e)[:500]}\nReturn ONLY the corrected JSON object."}]
        raise StructuredOutputError(str(err)[:500])


def _patterns(env: str) -> list[str]:
    return [p.strip() for p in os.getenv(env, "").split(",") if p.strip()]


def jev_plugin(role: str) -> dict:
    """The jev-router plugin for one role: its cost tier and the team's pool limits (OpenRouter docs)."""
    r = role.upper()
    tier = (os.getenv(f"{r}_JEV_COST_TIER") or os.getenv("JEV_COST_TIER") or JEV_TIERS.get(role.lower(), "")).lower()
    if tier and tier not in ("low", "medium", "high"):
        raise ValueError(f"JEV cost tier must be low, medium or high, not {tier!r}")
    plugin = {"id": "jev-router"}
    if tier:
        plugin["cost_tier"] = tier
    if models := _patterns(f"{r}_JEV_MODELS") or _patterns("JEV_MODELS"):
        plugin["models"] = models  # preferences: the router may still pick outside them if none is routable
    if excluded := _patterns("JEV_EXCLUDED_MODELS"):
        plugin["excluded_models"] = excluded  # hard: never selected
    return plugin


def get_llm(role: str = "default") -> LLM:
    """Provider: <ROLE>_PROVIDER, else LLM_PROVIDER.
    Model: <ROLE>_MODEL, else <PROVIDER>_MODEL (e.g. OPENAI_MODEL), else LLM_MODEL.
    With <ROLE>_ROUTING=jev or LLM_ROUTING=jev (and no <ROLE>_MODEL): OpenRouter's Jev Router picks the model.
    role = ROUTER | EXTRACTOR | CATEGORIZER | AGENT | EXPLAINER | REPORT_ORCHESTRATOR | REPORT_WORKER | ..."""
    r = role.upper()
    temp = os.getenv("LLM_TEMPERATURE", "0").strip()  # empty = let the provider use its default
    common = {"timeout": float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
              "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "2000")), "temperature": float(temp) if temp else None}
    routing = (os.getenv(f"{r}_ROUTING") or os.getenv("LLM_ROUTING", "")).strip().lower()
    if routing == "jev" and not os.getenv(f"{r}_MODEL"):
        llm = LLM("openrouter", JEV_MODEL, extra_body={"plugins": [jev_plugin(role)]},
                  fallback_model=os.getenv("JEV_FALLBACK_MODEL") or os.getenv("OPENROUTER_MODEL"), **common)
    else:
        if routing not in ("", "fixed", "jev"):
            raise ValueError(f"LLM_ROUTING must be 'jev' or 'fixed', not {routing!r}")
        provider = (os.getenv(f"{r}_PROVIDER") or os.getenv("LLM_PROVIDER", "openai")).strip().lower()
        model = os.getenv(f"{r}_MODEL") or os.getenv(f"{provider.upper()}_MODEL") or os.getenv("LLM_MODEL")
        if not model:
            raise RuntimeError(f"no model set: put {provider.upper()}_MODEL=<model name> in .env")
        llm = LLM(provider, model, **common)
    llm.fallbacks = fallback_llms(llm.provider, llm.model, common)
    return llm


def fallback_chain() -> list[tuple[str, str | None]]:
    """LLM_FALLBACK_PROVIDERS entries as (provider, model). An entry is "provider" (its <PROVIDER>_MODEL) or
    "provider:model" (that model; split at the first ':' because OpenRouter model ids contain ':free')."""
    out = []
    for entry in _patterns("LLM_FALLBACK_PROVIDERS"):
        provider, _, model = entry.partition(":")
        out.append((provider.strip().lower(), model.strip() or None))
    return out


def fallback_llms(primary: str, primary_model: str, common: dict) -> list[LLM]:
    """The next providers / models, in order, each with its key. Example (all free, renewing daily):
    LLM_FALLBACK_PROVIDERS=openrouter,groq,groq:openai/gpt-oss-120b,groq:qwen/qwen3.8-27b,openai
    Only providers in PROVIDERS; one without a key or model is skipped with a warning."""
    out, seen = [], {(primary, primary_model)}
    for p, model in fallback_chain():
        if p not in PROVIDERS:
            raise ValueError(f"LLM_FALLBACK_PROVIDERS: unknown provider '{p}'. Use one of {list(PROVIDERS)}")
        model = model or os.getenv(f"{p.upper()}_MODEL")
        if (p, model) in seen:
            continue
        if not model or not os.getenv(PROVIDERS[p]["key_env"]):
            log.warning("fallback %s skipped: set %s and %s_MODEL", p, PROVIDERS[p]["key_env"], p.upper())
            continue
        seen.add((p, model))
        out.append(LLM(p, model, **common))
    return out
