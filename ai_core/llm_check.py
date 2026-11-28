"""Which LLM provider / model will answer, and does each one still have free quota? Run from the repo root:

    python -m ai_core.llm_check          # free: what each role uses, the order, which keys are set (no request)
    python -m ai_core.llm_check --call   # + one tiny request per provider / model (uses one free request each)

With LLM_FALLBACK_PROVIDERS the app moves to the next provider / model when one answers 429 (free quota used up)
or 402 (no credit), and goes back to it by itself when its quota renews. Keys are never printed.
"""
import argparse
import os
import sys

import httpx
from dotenv import load_dotenv

from .llm import PROVIDERS, _human, fallback_chain, reset_seconds
from .tls import use_system_certs

ROLES = ["router", "extractor", "categorizer", "agent", "explainer",
         "report_orchestrator", "report_worker", "report_writer", "report_evaluator"]
BASE = {"openai": "https://api.openai.com/v1"}
EXAMPLE = "LLM_FALLBACK_PROVIDERS=openrouter,groq,groq:openai/gpt-oss-120b,groq:qwen/qwen3.8-27b,openai"
ADVICE = {
    401: "the key is wrong or revoked: create a new one with that provider and put it in .env",
    402: "no credit left on this key: keep it last in the order",
    403: "this key may not use that model: pick another model",
    404: "unknown model name: check the model in .env",
    429: "free quota used up: the app moves on to the next one in the order and comes back later by itself",
}


def _primary(role: str) -> tuple[str, str]:
    r = role.upper()
    provider = (os.getenv(f"{r}_PROVIDER") or os.getenv("LLM_PROVIDER", "openai")).strip().lower()
    model = os.getenv(f"{r}_MODEL") or os.getenv(f"{provider.upper()}_MODEL") or os.getenv("LLM_MODEL") or ""
    return provider, model


def _ready(provider: str, model: str | None) -> str:
    if provider not in PROVIDERS:
        return "NOT an approved provider"
    key = "key set" if os.getenv(PROVIDERS[provider]["key_env"]) else f"NO KEY ({PROVIDERS[provider]['key_env']})"
    return f"{key}, model {model or 'NO MODEL'}"


def ping(provider: str, model: str, client: httpx.Client) -> tuple[int, str]:
    """One tiny request. Returns (HTTP status, model that answered / when the quota comes back / the error)."""
    base = PROVIDERS[provider]["base_url"] or BASE[provider]
    body = {"model": model, "max_tokens": 5, "messages": [{"role": "user", "content": "Reply with the word OK."}]}
    resp = client.post(f"{base}/chat/completions", json=body,
                       headers={"Authorization": f"Bearer {os.getenv(PROVIDERS[provider]['key_env'], '')}"})
    if resp.status_code == 200:
        return 200, resp.json().get("model", "?")
    if resp.status_code == 429 and (wait := reset_seconds(resp.headers)) is not None:
        return 429, f"free quota used up, comes back by itself in {_human(wait)}"
    return resp.status_code, ADVICE.get(resp.status_code, resp.text[:200])


def entries() -> list[tuple[str, str]]:
    """The order the app tries: the main provider/model, then LLM_FALLBACK_PROVIDERS (duplicates removed)."""
    chain = [(p, m or os.getenv(f"{p.upper()}_MODEL") or "") for p, m in fallback_chain()]
    return list(dict.fromkeys([_primary("agent"), *chain]))


def check(call: bool, client: httpx.Client | None = None) -> int:
    load_dotenv()
    if client is None:
        print(f"system certificates: {'on' if use_system_certs() else 'off (USE_SYSTEM_CERTS)'}\n")
    print("1) What each role uses first")
    for role in ROLES:
        r = role.upper()
        routing = (os.getenv(f"{r}_ROUTING") or os.getenv("LLM_ROUTING", "")).lower()
        provider, model = _primary(role)
        first = "Jev Router (typesafe/jev-router)" if routing == "jev" and not os.getenv(f"{r}_MODEL") \
            else f"{provider}:{model}"
        print(f"   {role:<20} {first}")

    order = entries()
    print(f"\n2) Order when a free quota runs out: {' -> '.join(f'{p}:{m}' for p, m in order)}")
    if not fallback_chain():
        print("   Without LLM_FALLBACK_PROVIDERS a used-up daily quota stops the assistant.")
        print(f"   Example (all free): {EXAMPLE}")
    problems = 0
    for p, m in order:
        state = _ready(p, m)
        problems += "NO " in state or "NOT" in state
        print(f"   {p:<11} {state}")

    if not call:
        print("\n3) Skipped the test requests (add --call to send one tiny request to each).")
        return 1 if problems else 0
    print("\n3) One tiny request to each")
    client = client or httpx.Client(timeout=30)
    working = 0
    for p, m in order:
        if p not in PROVIDERS or not os.getenv(PROVIDERS[p]["key_env"]) or not m:
            print(f"   {p}:{m or '?'}  skipped (no key or model)")
            continue
        try:
            status, detail = ping(p, m, client)
        except httpx.HTTPError as e:
            print(f"   {p}:{m}  could not connect: {type(e).__name__} (certificate error? set USE_SYSTEM_CERTS=true)")
            continue
        if status == 200:
            working += 1
            print(f"   {p}:{m}  OK, answered by {detail}")
        else:
            print(f"   {p}:{m}  HTTP {status}: {detail}")
    print(f"\n   {working} of {len(order)} answered. A used-up free quota renews by itself; until then the next one "
          "in the order answers.")
    return 0 if working else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check the LLM providers, their keys and their free quota.")
    ap.add_argument("--call", action="store_true", help="send one tiny request to each provider / model")
    return check(ap.parse_args(argv).call)


if __name__ == "__main__":
    sys.exit(main())
