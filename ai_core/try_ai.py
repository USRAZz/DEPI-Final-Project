"""Local test harness for the AI part: no frontend and no API needed. Run from the repo root:
  python -m ai_core.try_ai route "كم صرفنا على الكهرباء؟"
  python -m ai_core.try_ai extract data/synthetic/invoices/inv4.jpg   (or a folder; add --labels to score accuracy)
  python -m ai_core.try_ai ask "Which invoices are flagged?" --role accountant
  python -m ai_core.try_ai report "تقرير مصروفات أكتوبر 2026"
  python -m ai_core.try_ai chat
  python -m ai_core.try_ai ocr data/synthetic/invoices/inv4.jpg
These call the real LLM from .env (they cost a little). The offline tests are in tests/ and services/*/tests.
"""
import argparse
import json
from pathlib import Path

from services.agent.app.agent_loop import run_agent
from services.agent.app.router import route_request
from services.agent.app.tools import Context
from services.extractor.app.pipeline import process_invoice

INVOICE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".pdf", ".txt"}
KEYS = ["vendor_name", "invoice_number", "invoice_date", "currency", "total_amount", "iban"]


def show(obj):
    print(json.dumps(obj if isinstance(obj, (dict, list)) else obj.model_dump(mode="json"), ensure_ascii=False, indent=2))


def _norm(s) -> str:
    return "".join(str(s).lower().split())


def same(key, got, expected):
    if got is None:
        return False
    if key == "total_amount":
        return abs(float(got) - float(expected)) < 0.01
    return _norm(got) == _norm(expected)


def cmd_route(a):
    show(route_request(a.message, has_attachment=a.attach))


def cmd_extract(a):
    p = Path(a.path)
    files = sorted(f for f in p.iterdir() if f.suffix.lower() in INVOICE_EXT) if p.is_dir() else [p]
    hits = {k: [0, 0] for k in KEYS}  # field -> [correct, total]
    for f in files:
        res = process_invoice(f)
        print(f"\n=== {f.name}: {res.status}  ({res.seconds}s, {res.usage.get('tokens')} tokens)")
        show(res)
        label = f.with_suffix(".json")  # ground truth next to the invoice: inv4.jpg + inv4.json
        if a.labels and label.exists():
            expected = json.loads(label.read_text(encoding="utf-8"))
            got = res.fields.model_dump(mode="json") if res.fields else {}
            for k in KEYS:
                if expected.get(k) is not None:
                    hits[k][1] += 1
                    hits[k][0] += same(k, got.get(k), expected[k])
    if a.labels:
        print("\n=== field accuracy")
        for k, (ok, total) in hits.items():
            if total:
                print(f"{k:16s} {ok}/{total}  {ok / total:.0%}")


def cmd_ask(a):
    r = run_agent(a.question, Context(role=a.role), language=a.lang)
    for s in r.trace:
        print(f"step {s['step']}: {s['thought']}  ->  {s.get('tool', 'FINAL')} {s.get('args', '')}")
    print(f"\n[{r.status}] {r.answer}")
    if r.proposal:
        show(r.proposal)
    print(f"\ntools={r.tools_used} steps={r.steps} tokens={r.tokens} seconds={r.seconds}")


def cmd_report(a):
    from services.agent.app.reports import generate_report

    r = generate_report(a.request, Context(role=a.role))
    print(r.markdown)
    print(f"\nquality={r.quality} rounds={r.rounds} models={r.models} notes={r.notes}")


def resolve_invoice_path(raw: str):
    """Accepts quoted paths and bare file names (looked up in the synthetic invoice folders)."""
    raw = raw.strip().strip("\"'")
    root = Path(__file__).resolve().parents[1]
    for base in (Path("."), root / "data" / "synthetic" / "invoices", root / "tests" / "fixtures" / "synthetic" / "invoices"):
        candidate = base / raw
        if candidate.is_file():
            return candidate
    return None


def cmd_chat(a):
    """Talks to the REAL /v1/chat code path (router, agent loop, proposals, alerts with reasons, chat memory)."""
    from fastapi.testclient import TestClient

    from services.agent.app.main import app as agent_app
    client = TestClient(agent_app)
    history: list[dict] = []
    print("SecureFin AI test chat (same code as the real /v1/chat). 'exit' to quit. 'upload <file>' sends an invoice.")
    while True:
        msg = input("\nyou> ").strip()
        if not msg:
            continue
        if msg.lower() in {"exit", "quit"}:
            break
        if msg.lower().startswith("upload "):
            path = resolve_invoice_path(msg[7:])
            if path is None:
                print("file not found. Use a full path, or put the file in data/synthetic/invoices and type only its name.")
                continue
            show(process_invoice(path))
            continue
        r = client.post("/v1/chat", json={"message": msg, "history": history[-10:]}, headers={"x-user-role": a.role})
        if r.status_code != 200:
            print("HTTP", r.status_code, r.text[:300])
            continue
        data = r.json()
        print(data["answer"])
        for action in data.get("proposed_actions", []):
            print("\nproposed action (the API forwards it to the gateway):")
            show(action)
        if data.get("sources"):
            print(f"\n(based on: {', '.join(data['sources'])})")
        history += [{"role": "user", "content": msg}, {"role": "assistant", "content": data["answer"][:4000]}]


def cmd_ocr(a):
    from services.extractor.app.ocr import extract_text
    print(extract_text(a.path))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Try the AI part locally (real LLM from .env).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("route")
    s.add_argument("message", nargs="?", default="")
    s.add_argument("--attach", action="store_true")
    s.set_defaults(fn=cmd_route)
    s = sub.add_parser("extract")
    s.add_argument("path")
    s.add_argument("--labels", action="store_true")
    s.set_defaults(fn=cmd_extract)
    s = sub.add_parser("ask")
    s.add_argument("question")
    s.add_argument("--role", default="accountant")
    s.add_argument("--lang", default="en")
    s.set_defaults(fn=cmd_ask)
    s = sub.add_parser("report")
    s.add_argument("request")
    s.add_argument("--role", default="accountant")
    s.set_defaults(fn=cmd_report)
    s = sub.add_parser("chat")
    s.add_argument("--role", default="accountant")
    s.set_defaults(fn=cmd_chat)
    s = sub.add_parser("ocr")
    s.add_argument("path")
    s.set_defaults(fn=cmd_ocr)
    return ap


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.fn(args)
