"""Local test harness for the AI part: no frontend and no API needed. Run from the repo root:
  python -m scripts.try_ai route "كم صرفنا على الكهرباء؟"
  python -m scripts.try_ai extract data/invoices/inv1.png        (or a folder; add --labels to score accuracy)
  python -m scripts.try_ai ask "Which invoices are flagged?" --role accountant
  python -m scripts.try_ai chat
"""
import argparse
import json
from pathlib import Path

from services.agent.app.agent_loop import run_agent
from services.agent.app.router import Route, route_request
from services.agent.app.tools import Context
from services.extractor.app.pipeline import process_invoice

INVOICE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".pdf", ".txt"}
KEYS = ["vendor_name", "invoice_number", "invoice_date", "currency", "total_amount", "iban"]


def show(obj):
    print(json.dumps(obj if isinstance(obj, (dict, list)) else obj.model_dump(mode="json"), ensure_ascii=False, indent=2))


def same(key, got, expected):
    if got is None:
        return False
    if key == "total_amount":
        return abs(float(got) - float(expected)) < 0.01
    norm = lambda s: "".join(str(s).lower().split())
    return norm(got) == norm(expected)


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
        label = f.with_suffix(".json")  # ground truth next to the invoice: inv1.png + inv1.json
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


def cmd_chat(a):
    ctx, history = Context(role=a.role), []
    print("SecureFin AI test chat. 'exit' to quit. 'upload <path>' sends an invoice.")
    while True:
        msg = input("\nyou> ").strip()
        if msg.lower() in {"exit", "quit"}:
            break
        upload = msg.lower().startswith("upload ")
        d = route_request("" if upload else msg, has_attachment=upload)
        print(f"[route={d.route.value} confidence={d.confidence} language={d.language}]")
        if d.route == Route.invoice_upload:
            show(process_invoice(msg[7:].strip() if upload else input("invoice path> ").strip()))
        elif d.route in (Route.finance_question, Route.payment_request):
            r = run_agent(msg, ctx, language=d.language, history=history[-6:])
            print(r.answer)
            if r.proposal:
                show(r.proposal)
            history += [{"role": "user", "content": msg}, {"role": "assistant", "content": r.answer}]
        elif d.route == Route.unclear:
            print(d.clarifying_question)
        else:
            print("(reports are not built yet)")

def cmd_ocr(a):
    from services.extractor.app.ocr import extract_text
    print(extract_text(a.path))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("route"); s.add_argument("message", nargs="?", default=""); s.add_argument("--attach", action="store_true"); s.set_defaults(fn=cmd_route)
    s = sub.add_parser("extract"); s.add_argument("path"); s.add_argument("--labels", action="store_true"); s.set_defaults(fn=cmd_extract)
    s = sub.add_parser("ask"); s.add_argument("question"); s.add_argument("--role", default="accountant"); s.add_argument("--lang", default="en"); s.set_defaults(fn=cmd_ask)
    s = sub.add_parser("chat"); s.add_argument("--role", default="accountant"); s.set_defaults(fn=cmd_chat)
    s = sub.add_parser("ocr"); s.add_argument("path"); s.set_defaults(fn=cmd_ocr)
    args = ap.parse_args()
    args.fn(args)