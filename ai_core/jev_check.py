"""Is Jev Router usable with this project's OpenRouter key? Run from the repo root:

    python -m ai_core.jev_check          # free: settings, catalogue, key (no chat call)
    python -m ai_core.jev_check --call   # + one tiny chat call through Jev (costs a fraction of a cent)

It prints what each role will use, whether `typesafe/jev-router` is in OpenRouter's public catalogue, whether the key
works and has credit, and (with --call) which model Jev picked, or the exact reason it refused (401/402/404/503) with
what to do. Nothing secret is printed: only the key's label and limits as OpenRouter reports them.
"""
import argparse
import json
import os
import sys

import httpx
from dotenv import load_dotenv

from .llm import JEV_MODEL, JEV_TIERS, jev_plugin
from .tls import use_system_certs

API = "https://openrouter.ai/api/v1"
ROLES = ["router", "extractor", "categorizer", "agent", "explainer",
         "report_orchestrator", "report_worker", "report_writer", "report_evaluator"]
ADVICE = {
    401: "The key is wrong or revoked. Create a new key at openrouter.ai (Keys) and put it in .env as OPENROUTER_API_KEY.",
    402: "The account has no credit left. Add credit on openrouter.ai, or set a lower limit on another key.",
    403: "This key or its workspace is not allowed to use the router or the models it picked. Check the key's and the "
         "workspace's model / provider restrictions on openrouter.ai.",
    404: "OpenRouter says this key cannot use Jev Router, or no model is left after your limits. The router works "
         "only in the global data region and in workspaces that allow it. Check, on openrouter.ai with the account "
         "that owns the key: (1) the workspace / organization allows the typesafe/jev-router model, (2) no "
         "allow-list or provider restriction on the key or workspace removes it or every model it may pick, "
         "(3) JEV_MODELS / JEV_EXCLUDED_MODELS in .env do not exclude everything. Until then the app uses "
         "JEV_FALLBACK_MODEL automatically.",
    503: "Jev Router is temporarily unavailable. Nothing to change: the app uses JEV_FALLBACK_MODEL and retries Jev "
         "after JEV_RETRY_SECONDS.",
}


def _role_line(role: str) -> str:
    r = role.upper()
    routing = (os.getenv(f"{r}_ROUTING") or os.getenv("LLM_ROUTING", "")).strip().lower()
    if os.getenv(f"{r}_MODEL"):
        return f"{role:<20} fixed model {os.getenv(f'{r}_MODEL')} ({r}_MODEL wins over Jev)"
    if routing == "jev":
        try:
            plugin = jev_plugin(role)
        except ValueError as e:
            return f"{role:<20} ERROR {e}"
        return f"{role:<20} Jev, cost tier {plugin.get('cost_tier', 'default')}" + (
            f", pool {plugin['models']}" if "models" in plugin else "")
    provider = os.getenv(f"{r}_PROVIDER") or os.getenv("LLM_PROVIDER", "openai")
    model = os.getenv(f"{provider.upper()}_MODEL") or os.getenv("LLM_MODEL") or "(none set)"
    return f"{role:<20} fixed model {model} via {provider} (Jev off: set LLM_ROUTING=jev)"


def check(call: bool, client: httpx.Client | None = None) -> int:
    load_dotenv()
    if client is None:
        print(f"system certificates: {'on' if use_system_certs() else 'off (USE_SYSTEM_CERTS)'}\n")
    client = client or httpx.Client(timeout=30)
    problems = 0
    print("1) What each role uses")
    for role in ROLES:
        print("   " + _role_line(role))
    fallback = os.getenv("JEV_FALLBACK_MODEL") or os.getenv("OPENROUTER_MODEL")
    print(f"   fallback when Jev refuses: {fallback or 'NONE (set JEV_FALLBACK_MODEL or OPENROUTER_MODEL)'}")
    if not fallback:
        problems += 1
    if os.getenv("JEV_EXCLUDED_MODELS"):
        print(f"   excluded everywhere: {os.getenv('JEV_EXCLUDED_MODELS')}")
    print(f"   default tiers: {JEV_TIERS}")

    print("\n2) Is Jev in OpenRouter's public catalogue?")
    try:
        models = client.get(f"{API}/models").json().get("data", [])
        listed = any(m.get("id") == JEV_MODEL for m in models)
        print(f"   {JEV_MODEL}: {'listed' if listed else 'NOT listed'} ({len(models)} models in the catalogue)")
        problems += not listed
    except (httpx.HTTPError, ValueError) as e:
        print(f"   could not read the catalogue: {type(e).__name__}: {e}")
        if "CERTIFICATE" in str(e).upper():
            print("   A proxy or antivirus inspects HTTPS on this machine, so every LLM call fails the same way.")
            print("   Fix: pip install truststore, then set USE_SYSTEM_CERTS=true in .env (ai_core/tls.py).")
        return 1

    key = os.getenv("OPENROUTER_API_KEY", "")
    print("\n3) The key in .env")
    if not key:
        print("   OPENROUTER_API_KEY is empty: Jev cannot be used. Put an OpenRouter key in .env.")
        return 1
    resp = client.get(f"{API}/key", headers={"Authorization": f"Bearer {key}"})
    if resp.status_code != 200:
        print(f"   OpenRouter answered {resp.status_code}. {ADVICE.get(resp.status_code, resp.text[:200])}")
        return 1
    info = resp.json().get("data", {})
    limit = info.get("limit")
    print(f"   key '{info.get('label', '?')}': used {info.get('usage', '?')} credits, "
          f"limit {limit if limit is not None else 'none'}, free tier: {info.get('is_free_tier', '?')}")
    if limit is not None and info.get("limit_remaining") is not None and info["limit_remaining"] <= 0:
        print(f"   {ADVICE[402]}")
        problems += 1

    if not call:
        print("\n4) Skipped the test call (add --call to make one tiny request through Jev).")
        return 1 if problems else 0

    print("\n4) One tiny request through Jev")
    body = {"model": JEV_MODEL, "max_tokens": 5, "plugins": [jev_plugin("router")],
            "messages": [{"role": "user", "content": "Reply with the word OK."}]}
    resp = client.post(f"{API}/chat/completions", json=body,
                       headers={"Authorization": f"Bearer {key}", "X-OpenRouter-Metadata": "enabled"})
    if resp.status_code == 200:
        data = resp.json()
        print(f"   Jev works. It picked: {data.get('model')}")
        meta = data.get("openrouter_metadata") or {}
        print(f"   router details: {json.dumps(meta, ensure_ascii=False)[:400]}" if meta else "")
        return 1 if problems else 0
    print(f"   OpenRouter answered {resp.status_code}: {resp.text[:300]}")
    print(f"   What to do: {ADVICE.get(resp.status_code, 'see the message above.')}")
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check that Jev Router works with this project's OpenRouter key.")
    ap.add_argument("--call", action="store_true", help="also make one tiny chat call through Jev")
    return check(ap.parse_args(argv).call)


if __name__ == "__main__":
    sys.exit(main())
