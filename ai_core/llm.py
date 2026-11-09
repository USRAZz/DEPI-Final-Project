"""LLM client for the OpenAI chat-completions API. The model comes from .env.
Every message is masked with ai_core.privacy before it leaves the process."""
import json
import os
import time
from dataclasses import asdict, dataclass, field

from dotenv import load_dotenv
from openai import BadRequestError, NotFoundError, OpenAI, RateLimitError

from .privacy import mask_messages

load_dotenv()

# Decision (SecureFin plan 1.2): OpenAI only. Every message is masked (ai_core.privacy) before it is sent.
PROVIDERS = {
    "openai": {"base_url": None, "key_env": "OPENAI_API_KEY"},
}


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

    def as_dict(self):
        return asdict(self)


def _extract_json(text: str) -> dict:
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        raise ValueError("no JSON object found in the reply")
    return json.loads(text[s:e + 1])  # also strips ```json fences


class LLM:
    def __init__(self, provider: str, model: str, *, timeout: float = 60.0, max_tokens: int = 2000,
                 temperature: float | None = 0.0):
        cfg = PROVIDERS.get(provider)
        if cfg is None:
            raise ValueError(f"unknown provider '{provider}'. Use one of {list(PROVIDERS)}")
        key = os.getenv(cfg["key_env"])
        if not key:
            raise RuntimeError(f"missing {cfg['key_env']} in .env")
        self.provider, self.model = provider, model
        self.client = OpenAI(api_key=key, base_url=cfg["base_url"], timeout=timeout)
        # request options; auto-corrected below when a provider/model rejects one of them
        self.opts = {"temperature": temperature, "max_tokens": max_tokens, "tokens_param": "max_tokens", "json_mode": True}
        self.usage = Usage()
    
    def _create(self, kw: dict):
        for wait in (0, 4, 12, 30):  # free tiers rate-limit often: wait, then retry
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
        if budget:
            budget.check()
        kw = {"model": self.model, "messages": mask_messages(messages), self.opts["tokens_param"]: self.opts["max_tokens"]}
        if self.opts["temperature"] is not None:
            kw["temperature"] = self.opts["temperature"]
        if json_mode and self.opts["json_mode"]:
            kw["response_format"] = {"type": "json_object"}
        t0 = time.perf_counter()
        r = self._create(kw)
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


def get_llm(role: str = "default") -> LLM:
    """Provider: <ROLE>_PROVIDER, else LLM_PROVIDER.
    Model: <ROLE>_MODEL, else <PROVIDER>_MODEL (e.g. OPENAI_MODEL), else LLM_MODEL.  role = ROUTER | EXTRACTOR | CATEGORIZER | AGENT"""
    r = role.upper()
    provider = os.getenv(f"{r}_PROVIDER") or os.getenv("LLM_PROVIDER", "openai")
    model = os.getenv(f"{r}_MODEL") or os.getenv(f"{provider.upper()}_MODEL") or os.getenv("LLM_MODEL")
    if not model:
        raise RuntimeError(f"no model set: put {provider.upper()}_MODEL=<model name> in .env")
    temp = os.getenv("LLM_TEMPERATURE", "0").strip()  # empty = let the provider use its default
    return LLM(provider, model, timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
               max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2000")),
               temperature=float(temp) if temp else None)