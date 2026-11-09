"""Agent tools. All READ-ONLY. The data source is switchable:
BACKEND=mock (default, local sample data) or BACKEND=api (Karim's API, called with the user's own token)."""
import ast
import operator
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Context:
    user_id: str = "demo-user"
    company_id: str = "demo-co"
    role: str = "accountant"
    token: str | None = None  # the logged-in user's token; the real API enforces permissions with it


# ---------------------------------------------------------------- data backends
def _filter(rows: list[dict], date_key: str, f: dict) -> list[dict]:
    out = []
    for r in sorted(rows, key=lambda r: r[date_key], reverse=True):
        if f.get("vendor_name") and str(f["vendor_name"]).lower() not in r.get("vendor_name", "").lower():
            continue
        if f.get("status") and str(f["status"]).upper() != str(r.get("status", "")).upper():
            continue
        if f.get("date_from") and r[date_key] < f["date_from"]:
            continue
        if f.get("date_to") and r[date_key] > f["date_to"]:
            continue
        out.append(r)
    return out[: int(f.get("limit") or 20)]


class MockBackend:
    # Integer ids, like the real api. vendor_id lets the assistant fill a valid create_payment_request proposal.
    INVOICES = [
        {"id": 1, "vendor_id": 1, "vendor_name": "Nile Office Supplies", "invoice_number": "A-1001",
         "invoice_date": "2026-10-03", "total_amount": 12500.0, "currency": "EGP", "status": "READY",
         "category": "office_supplies"},
        {"id": 2, "vendor_id": 2, "vendor_name": "Delta Telecom", "invoice_number": "7781", "invoice_date": "2026-10-10",
         "total_amount": 3400.0, "currency": "EGP", "status": "READY", "category": "utilities"},
        {"id": 3, "vendor_id": 1, "vendor_name": "Nile Office Supplies", "invoice_number": "A-1001",
         "invoice_date": "2026-10-12", "total_amount": 12500.0, "currency": "EGP", "status": "FLAGGED",
         "category": "office_supplies"},
        {"id": 4, "vendor_id": 3, "vendor_name": "Cairo Cloud Hosting", "invoice_number": "CH-55",
         "invoice_date": "2026-09-28", "total_amount": 48000.0, "currency": "EGP", "status": "READY",
         "category": "software"},
    ]
    TRANSACTIONS = [
        {"date": "2026-10-05", "invoice_id": 1, "amount": 12500.0, "status": "paid"},
        {"date": "2026-10-15", "invoice_id": 2, "amount": 3400.0, "status": "paid"},
    ]
    # Same scale as the risk service: score 0-100.
    RISK = {3: {"score": 70, "level": "high", "rule_hits": ["DUPLICATE_INVOICE"],
                "reasons": ["Same vendor and invoice number as invoice 1"]}}

    def get_invoices(self, ctx: Context, filters: dict):
        return _filter(self.INVOICES, "invoice_date", filters)

    def get_transactions(self, ctx: Context, date_from=None, date_to=None):
        return _filter(self.TRANSACTIONS, "date", {"date_from": date_from, "date_to": date_to})

    def get_risk_score(self, ctx: Context, invoice_id: str):
        return self.RISK.get(int(invoice_id), {"score": 0, "level": "low", "rule_hits": [], "reasons": []})


class ApiBackend:
    """Calls the real API with the user's token. TODO: align PATHS with Karim's real endpoints."""
    PATHS = {"invoices": "/invoices", "transactions": "/transactions", "risk": "/risk/{invoice_id}"}

    def __init__(self, base_url: str | None = None):
        self.base = (base_url or os.getenv("API_BASE_URL", "http://localhost:8000")).rstrip("/")

    def _get(self, ctx: Context, path: str, params: dict | None = None):
        import httpx
        headers = {"Authorization": f"Bearer {ctx.token}"} if ctx.token else {}
        r = httpx.get(self.base + path, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()

    def get_invoices(self, ctx, filters):
        return self._get(ctx, self.PATHS["invoices"], filters)

    def get_transactions(self, ctx, date_from=None, date_to=None):
        return self._get(ctx, self.PATHS["transactions"], {"date_from": date_from, "date_to": date_to})

    def get_risk_score(self, ctx, invoice_id):
        return self._get(ctx, self.PATHS["risk"].format(invoice_id=invoice_id))


def get_backend():
    return ApiBackend() if os.getenv("BACKEND", "mock").lower() == "api" else MockBackend()


# ---------------------------------------------------------------- calculate (safe, no eval)
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
        ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"round": round, "abs": abs, "min": min, "max": max, "sum": lambda *a: sum(a)}


def calculate(expression: str):
    if len(expression) > 200:
        raise ValueError("expression too long")

    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 10:
                raise ValueError("exponent too large")
            return _OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError("unsupported expression")

    return ev(ast.parse(expression.strip(), mode="eval").body)


# ---------------------------------------------------------------- search_policies (light retrieval, no embeddings)
def _policy_chunks(path: Path) -> list[str]:
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    chunks: list[str] = []

    def walk(node, trail):
        where = " > ".join(trail)
        if isinstance(node, dict) and all(not isinstance(v, (dict, list)) for v in node.values()):
            chunks.append(f"{where}: " + ", ".join(f"{k}={v}" for k, v in node.items()))
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(v, trail + [str(k)])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, trail + [f"[{i}]"])
        else:
            chunks.append(f"{where}: {node}")

    walk(data, [])
    return chunks


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[^\W_]+", text.lower())  # splits snake_case too, works for Arabic
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words}


def search_policies(query: str, top: int = 3):
    path = Path(os.getenv("POLICIES_FILE") or Path(__file__).resolve().parents[3] / "policies" / "payments.yaml")
    if not path.exists():
        return {"error": f"policies file not found: {path}"}
    words = _tokens(query)
    scored = sorted(((len(words & _tokens(c)), c) for c in _policy_chunks(path)), reverse=True)
    hits = [c for s, c in scored[:top] if s > 0]
    return hits or {"result": "no matching policy found"}


# ---------------------------------------------------------------- registry
@dataclass
class Tool:
    name: str
    description: str
    args: dict[str, str]
    fn: Callable[..., Any]


class ToolRegistry:
    def __init__(self, backend=None):
        b = backend or get_backend()
        self._tools: dict[str, Tool] = {}
        self.add("get_invoices", "List invoices of the company, newest first.",
                 {"vendor_name": "optional text", "status": "optional: READY | FLAGGED | FAILED",
                  "date_from": "optional YYYY-MM-DD", "date_to": "optional YYYY-MM-DD", "limit": "optional max rows"},
                 lambda ctx, **f: b.get_invoices(ctx, f))
        self.add("get_transactions", "List payments made in a date range.",
                 {"date_from": "optional YYYY-MM-DD", "date_to": "optional YYYY-MM-DD"},
                 lambda ctx, **kw: b.get_transactions(ctx, kw.get("date_from"), kw.get("date_to")))
        self.add("search_policies", "Find company payment-policy rules (limits, approvals, holds) relevant to a question.",
                 {"query": "what you are looking for"}, lambda ctx, query: search_policies(query))
        self.add("get_risk_score", "Risk score and reasons for one invoice.",
                 {"invoice_id": "integer invoice id, e.g. 3"}, lambda ctx, invoice_id: b.get_risk_score(ctx, invoice_id))
        self.add("calculate", "Safe calculator for arithmetic (no thousands separators).",
                 {"expression": "e.g. 12500 + 3400"}, lambda ctx, expression: {"result": calculate(expression)})

    def add(self, name, description, args, fn):
        self._tools[name] = Tool(name, description, args, fn)

    def names(self) -> list[str]:
        return list(self._tools)

    def describe(self) -> str:
        """Text for the prompt, generated from the registry: add a tool and the prompt updates itself."""
        lines = []
        for t in self._tools.values():
            args = ", ".join(f"{k}: {v}" for k, v in t.args.items())
            lines.append(f"- {t.name}({args}): {t.description}")
        return "\n".join(lines)

    def call(self, name: str, args: dict | None, ctx: Context):
        if name not in self._tools:
            raise KeyError(f"unknown tool '{name}'. Available tools: {self.names()}")
        return self._tools[name].fn(ctx, **(args or {}))