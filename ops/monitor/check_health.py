"""One-shot health check of a running SecureFin stack (owner: M4 Ziad). Standard library only.

    python ops/monitor/check_health.py                      # docker compose on this machine (ports 8000-8004)
    python ops/monitor/check_health.py --base 192.168.1.20 --json   # another machine running local compose
    AUDIT_VERIFY_TOKEN=... python ops/monitor/check_health.py --audit-companies 1,2

Checks GET /health on every service (HTTP 200 and {"status": "ok"}) and, when --audit-companies and
AUDIT_VERIFY_TOKEN are given, that the gateway's audit hash chain verifies for each company.
Prints one line per check; exit 0 = all OK, 1 = something is down or broken. Never prints the token.
Workflow n8n/workflows/4-health-watch.json runs the same checks every 5 minutes and alerts.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

# name -> host port in docker compose (services/<name>/compose.yaml)
PORTS = {"api": 8000, "agent": 8001, "gateway": 8002, "risk": 8003, "extractor": 8004}


def _call(url: str, timeout: float, body: dict | None = None, token: str = "") -> tuple[int | None, dict, float, str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json", **({"X-Service-Token": token} if token else {})})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return None, {}, time.monotonic() - started, str(getattr(e, "reason", e))
    ms = time.monotonic() - started
    try:
        return status, json.loads(raw or b"{}"), ms, ""
    except ValueError:
        return status, {}, ms, "answer is not JSON"


def check_service(name: str, url: str, timeout: float) -> dict:
    status, body, secs, err = _call(url, timeout)
    ok = status == 200 and body.get("status") == "ok"
    detail = err or (f"HTTP {status}" if status != 200 else "" if ok else f"status={body.get('status')!r}")
    return {"check": f"health:{name}", "ok": ok, "ms": round(secs * 1000), "detail": detail or "ok"}


def check_audit(base_url: str, company: int, token: str, timeout: float) -> dict:
    status, body, secs, err = _call(f"{base_url}/v1/audit/verify", timeout, {"company_id": company}, token)
    ok = status == 200 and body.get("ok") is True
    if err or status != 200:
        detail = err or f"HTTP {status}"
    elif ok:
        detail = f"{body.get('entries')} entries, chain intact"
    else:
        detail = f"chain BROKEN at entry id {body.get('first_broken_id')}"
    return {"check": f"audit:company {company}", "ok": ok, "ms": round(secs * 1000), "detail": detail}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="localhost", help="host the service ports are on (default localhost)")
    ap.add_argument("--url", action="append", default=[], metavar="NAME=URL",
                    help="health URL of one service, instead of --base + port (repeatable)")
    ap.add_argument("--audit-companies", default=os.environ.get("N8N_AUDIT_COMPANY_IDS", ""))
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    urls = {name: f"http://{args.base}:{port}/health" for name, port in PORTS.items()}
    if args.url:
        urls = dict(item.split("=", 1) for item in args.url)
    results = [check_service(name, url, args.timeout) for name, url in urls.items()]

    token = os.environ.get("AUDIT_VERIFY_TOKEN", "")
    companies = [int(c) for c in args.audit_companies.split(",") if c.strip()]
    if companies and not token:
        results.append({"check": "audit", "ok": False, "ms": 0, "detail": "AUDIT_VERIFY_TOKEN is not set"})
    elif companies:
        gateway = urls.get("gateway", f"http://{args.base}:{PORTS['gateway']}/health").rsplit("/health", 1)[0]
        results += [check_audit(gateway, c, token, args.timeout) for c in companies]

    healthy = all(r["ok"] for r in results)
    if args.json:
        print(json.dumps({"ok": healthy, "checks": results}, indent=2))
    else:
        for r in results:
            print(f"{'OK  ' if r['ok'] else 'FAIL'}  {r['check']:<20} {r['ms']:>5} ms  {r['detail']}")
        print("ALL OK" if healthy else "SOMETHING IS DOWN")
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
