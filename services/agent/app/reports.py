"""Reports (F6): pattern ④ orchestrator-workers + evaluator-optimizer (plan §5, flowchart workflow ④).

    ORCHESTRATOR (LLM)  reads the request, picks the sections and the period (from a fixed catalogue)
    facts (code)        each section's numbers, computed from the read-only tools (MockBackend or the api)
    WORKERS (LLM, in parallel)  one section each, written from its facts only
    SYNTHESIZER (LLM)   title + summary over the sections -> draft
    EVALUATOR           code: every number in the draft exists in the facts, every section is there, right script;
                        then LLM: clear, complete, consistent?
    OPTIMIZER (LLM)     revises the draft with the feedback; at most 3 evaluation rounds

Numbers never come from the model: a draft with a number that is not in the data is not shown. If no draft passes
the code check, the report is the fixed wording built from the facts (quality = "fallback"). Read-only: a report
decides nothing. With LLM_ROUTING=jev each role's call goes to Jev Router, which picks the model (ai_core/llm.py).
"""
import json
import logging
import os
import re
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import get_args

from pydantic import BaseModel, Field
from securefin_contracts import Language, Report, ReportSection, ReportSectionKey

from ai_core.llm import Budget, BudgetExceeded, get_llm
from ai_core.privacy import normalize_digits
from ai_core.prompts import load_prompt, untrusted

from .explain import meaning, no_code_reason
from .router import detect_language
from .tools import Context, get_backend

log = logging.getLogger(__name__)

SECTION_KEYS: tuple[str, ...] = get_args(ReportSectionKey)
SECTION_HELP = {
    "spending_summary": "money paid and invoiced in the period",
    "top_vendors": "the vendors with the largest invoiced amounts",
    "categories": "invoiced amounts by expense category",
    "anomalies": "flagged invoices and their risk reasons",
    "unpaid_invoices": "invoices in the period with no payment yet",
    "trend": "invoiced and paid amounts month by month",
}
DEFAULT_SECTIONS = ["spending_summary", "top_vendors", "anomalies"]
MAX_ROUNDS = 3
MAX_DAYS = 366
_ARABIC = re.compile(r"[؀-ۿ]")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


# ------------------------------------------------------------------------------------------------ LLM replies

class Plan(BaseModel):
    sections: list[str] = Field(min_length=1)
    date_from: date
    date_to: date
    title: str = Field(default="", max_length=200)


class SectionText(BaseModel):
    heading: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)


class DraftSection(BaseModel):
    key: str
    heading: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)


class Draft(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=2000)
    sections: list[DraftSection]


class Review(BaseModel):
    passes: bool
    feedback: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------------------------------------ plan

def _previous_month(today: date) -> tuple[date, date]:
    end = today.replace(day=1) - timedelta(days=1)
    return end.replace(day=1), end


def checked_plan(plan: Plan | None, today: date) -> tuple[list[str], date, date, str, list[str]]:
    """The orchestrator's plan with unknown sections dropped and the period made safe; notes say what changed."""
    notes = []
    if plan is None:
        start, end = _previous_month(today)
        return list(DEFAULT_SECTIONS), start, end, "", ["the request could not be planned: default sections and period"]
    sections = list(dict.fromkeys(s for s in plan.sections if s in SECTION_KEYS))
    if dropped := [s for s in plan.sections if s not in SECTION_KEYS]:
        notes.append(f"unknown sections ignored: {dropped}")
    if not sections:
        sections = list(DEFAULT_SECTIONS)
    start, end = plan.date_from, min(plan.date_to, today)
    if start > end or (end - start).days > MAX_DAYS:
        start, end = _previous_month(today)
        notes.append("the requested period was not valid: previous month used")
    return sections, start, end, plan.title, notes


# ------------------------------------------------------------------------------------------------ facts (code)

def _amount(v) -> Decimal:
    try:
        return Decimal(str(v)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        return Decimal("0")


def _num(d: Decimal):
    """JSON-friendly: an int when whole, else a 2-decimal string-free float."""
    return int(d) if d == d.to_integral_value() else float(d)


def _share(part: Decimal, whole: Decimal) -> float:
    return float((part * 100 / whole).quantize(Decimal("0.1"))) if whole else 0.0


def load_data(backend, ctx: Context, start: date, end: date) -> dict:
    f, t = start.isoformat(), end.isoformat()
    invoices = backend.get_invoices(ctx, {"date_from": f, "date_to": t, "limit": 1000}) or []
    payments = backend.get_transactions(ctx, f, t) or []
    paid_ids = {p.get("invoice_id") for p in backend.get_transactions(ctx, f, None) or []}
    return {"invoices": invoices, "payments": payments, "paid_invoice_ids": paid_ids}


def compute_facts(key: str, data: dict, backend, ctx: Context, start: date, end: date,
                  lang: str = "en") -> dict:
    inv = [i for i in data["invoices"] if (i.get("currency") or "EGP") == "EGP"]
    pay = list(data["payments"])
    invoiced = sum((_amount(i.get("total_amount")) for i in inv), Decimal("0"))
    other_currency = len(data["invoices"]) - len(inv)
    if key == "spending_summary":
        paid = sum((_amount(p.get("amount")) for p in pay), Decimal("0"))
        return {"currency": "EGP", "paid_total": _num(paid), "payments_count": len(pay),
                "invoiced_total": _num(invoiced), "invoices_count": len(inv),
                "invoices_in_other_currencies": other_currency}
    if key == "top_vendors":
        by_vendor: dict[str, list] = defaultdict(lambda: [Decimal("0"), 0])
        for i in inv:
            by_vendor[i.get("vendor_name") or "?"][0] += _amount(i.get("total_amount"))
            by_vendor[i.get("vendor_name") or "?"][1] += 1
        top = sorted(by_vendor.items(), key=lambda kv: kv[1][0], reverse=True)[:5]
        return {"currency": "EGP", "vendors": [{"vendor": v, "total": _num(s), "invoices": n,
                                                "share_pct": _share(s, invoiced)} for v, (s, n) in top]}
    if key == "categories":
        by_cat: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for i in inv:
            by_cat[i.get("category") or "other"] += _amount(i.get("total_amount"))
        return {"currency": "EGP", "categories": [{"category": c, "total": _num(s), "share_pct": _share(s, invoiced)}
                                                  for c, s in sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True)]}
    if key == "anomalies":
        rows = []
        for i in data["invoices"][:50]:
            risk = backend.get_risk_score(ctx, i["id"]) or {}
            codes = list(dict.fromkeys([*risk.get("rule_hits", []), *i.get("extraction_issues", [])]))
            if i.get("status") != "FLAGGED" and not codes and str(risk.get("level") or "low").lower() == "low":
                continue
            rows.append({"invoice_id": i["id"], "invoice_number": i.get("invoice_number"),
                         "vendor": i.get("vendor_name"), "total": _num(_amount(i.get("total_amount"))),
                         "currency": i.get("currency") or "EGP", "status": i.get("status"),
                         "risk_level": risk.get("level"),
                         "score": risk.get("score"),
                         # why it is suspicious, in the report's language (risk rules + invoice reader issues)
                         "reasons": [meaning(c, lang) for c in codes]
                                    or [no_code_reason(str(risk.get("level") or "").lower(), lang)]})
        return {"flagged": rows}
    if key == "unpaid_invoices":
        unpaid = [i for i in inv if i["id"] not in data["paid_invoice_ids"] and i.get("status") != "FLAGGED"]
        total = sum((_amount(i.get("total_amount")) for i in unpaid), Decimal("0"))
        return {"currency": "EGP", "unpaid_total": _num(total), "unpaid": [
            {"invoice_id": i["id"], "invoice_number": i.get("invoice_number"), "vendor": i.get("vendor_name"),
             "total": _num(_amount(i.get("total_amount"))), "invoice_date": i.get("invoice_date")} for i in unpaid]}
    if key == "trend":
        months: dict[str, list] = defaultdict(lambda: [Decimal("0"), Decimal("0")])
        for i in inv:
            months[str(i.get("invoice_date", ""))[:7]][0] += _amount(i.get("total_amount"))
        for p in pay:
            months[str(p.get("date", ""))[:7]][1] += _amount(p.get("amount"))
        return {"currency": "EGP", "months": [{"month": m, "invoiced": _num(a), "paid": _num(b)}
                                              for m, (a, b) in sorted(months.items()) if m]}
    raise KeyError(key)


# ------------------------------------------------------------------------------------------------ code checks

def _numbers(text: str) -> list[Decimal]:
    s = re.sub(r"(?<=\d)[,٬](?=\d{3})", "", normalize_digits(text or "")).replace("٫", ".")
    return [Decimal(n).normalize() for n in _NUMBER.findall(s)]


def allowed_numbers(facts: dict[str, dict], start: date, end: date) -> set[Decimal]:
    """Every number a correct report may print: the facts (with their usual roundings), the period, 0-10."""
    allowed = {Decimal(n) for n in range(11)}
    text = json.dumps(facts, ensure_ascii=False) + f" {start.isoformat()} {end.isoformat()}"
    for n in _numbers(text):
        allowed |= {n, n.quantize(Decimal("1")).normalize(), n.quantize(Decimal("0.1")).normalize()}
    for d in (start, end):
        allowed |= {Decimal(d.day), Decimal(d.month), Decimal(d.year)}
    return {a.normalize() for a in allowed}


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def check_draft(draft: Draft, keys: list[str], facts: dict[str, dict], lang: str, start: date, end: date) -> list[str]:
    """Problems code can prove; [] = the draft may go to the LLM evaluator."""
    problems = []
    if [s.key for s in draft.sections] != keys:
        problems.append(f"sections must be exactly {keys} in this order, got {[s.key for s in draft.sections]}")
    allowed = allowed_numbers(facts, start, end)
    texts = [draft.title, draft.summary, *(f"{s.heading}\n{s.body}" for s in draft.sections)]
    unknown = sorted({str(n) for t in texts for n in _numbers(t) if n.normalize() not in allowed})
    if unknown:
        problems.append(f"numbers not in the data: {unknown[:10]}; use only the numbers in the facts")
    names = sorted({v for v in _strings(facts) if len(v) > 1}, key=len, reverse=True)
    for t in texts:
        for name in names:  # vendor names and categories from the data may be in either script
            t = t.replace(name, " ")
        has_ar = bool(_ARABIC.search(t))
        if (lang == "ar") != has_ar:
            problems.append(f"text not in {'Arabic' if lang == 'ar' else 'English'}: {t[:60]!r}")
            break
    return problems


# ------------------------------------------------------------------------------------------------ fixed wording

def _money(v, lang: str) -> str:
    return f"{Decimal(str(v)):,.2f}".rstrip("0").rstrip(".") + (" جنيه" if lang == "ar" else " EGP")


HEADINGS = {
    "spending_summary": {"en": "Spending summary", "ar": "ملخص المصروفات"},
    "top_vendors": {"en": "Top vendors", "ar": "أكبر الموردين"},
    "categories": {"en": "Spending by category", "ar": "المصروفات حسب الفئة"},
    "anomalies": {"en": "Alerts", "ar": "التنبيهات"},
    "unpaid_invoices": {"en": "Unpaid invoices", "ar": "فواتير لسه متدفعتش"},
    "trend": {"en": "Month by month", "ar": "شهر بشهر"},
}


def template_section(key: str, f: dict, lang: str) -> str:
    ar = lang == "ar"
    if key == "spending_summary":
        return (f"- {'المدفوع' if ar else 'Paid'}: {_money(f['paid_total'], lang)} "
                f"({f['payments_count']} {'دفعة' if ar else 'payments'})\n"
                f"- {'الفواتير' if ar else 'Invoiced'}: {_money(f['invoiced_total'], lang)} "
                f"({f['invoices_count']} {'فاتورة' if ar else 'invoices'})")
    rows = {"top_vendors": f.get("vendors"), "categories": f.get("categories"), "anomalies": f.get("flagged"),
            "unpaid_invoices": f.get("unpaid"), "trend": f.get("months")}[key]
    if not rows:
        return "مفيش بيانات للفترة دي." if ar else "No data for this period."
    if key == "top_vendors":
        return "\n".join(f"- {r['vendor']}: {_money(r['total'], lang)} ({r['share_pct']}%)" for r in rows)
    if key == "categories":
        return "\n".join(f"- {r['category']}: {_money(r['total'], lang)} ({r['share_pct']}%)" for r in rows)
    if key == "anomalies":
        word = "فاتورة" if ar else "Invoice"
        return "\n".join(f"- {word} {r['invoice_number']} ({r['vendor']}, {_money(r['total'], lang)}): "
                         + " ".join(r["reasons"]) for r in rows)
    if key == "unpaid_invoices":
        return "\n".join(f"- {r['invoice_number']} ({r['vendor']}): {_money(r['total'], lang)}" for r in rows)
    return "\n".join(f"- {r['month']}: {_money(r['invoiced'], lang)} / {_money(r['paid'], lang)}" for r in rows)


def template_report(keys, facts, lang, start, end, title) -> tuple[str, str, list[ReportSection]]:
    sections = [ReportSection(key=k, heading=HEADINGS[k][lang], body=template_section(k, facts[k], lang),
                              facts=facts[k]) for k in keys]
    title = title or (f"تقرير {start} إلى {end}" if lang == "ar" else f"Report {start} to {end}")
    summary = (f"تقرير الفترة من {start} إلى {end}، مكتوب من البيانات مباشرة." if lang == "ar"
               else f"Report for {start} to {end}, written directly from the data.")
    return title, summary, sections


def to_markdown(r: Report) -> str:
    parts = [f"# {r.title}", f"_{r.date_from} → {r.date_to}_", "", r.summary]
    for s in r.sections:
        parts += ["", f"## {s.heading}", s.body]
    return "\n".join(parts)


# ------------------------------------------------------------------------------------------------ pipeline

def generate_report(request: str, ctx: Context | None = None, *, backend=None, today: date | None = None,
                    llms: dict[str, Callable] | None = None, budget: Budget | None = None) -> Report:
    """llms: optional role -> factory (tests); otherwise get_llm(role), which may route through Jev."""
    ctx, backend, today = ctx or Context(), backend or get_backend(), today or date.today()
    lang = detect_language(request)
    language = Language(lang)
    budget = budget or Budget(max_tokens=int(os.getenv("REPORT_MAX_TOKENS", "40000")),
                              max_seconds=float(os.getenv("REPORT_MAX_SECONDS", "150")))
    made: list = []

    def llm(role: str):
        client = (llms or {}).get(role, lambda: get_llm(role))()
        made.append(client)
        return client

    def ask(role: str, system: str, payload, schema):
        return llm(role).structured([{"role": "system", "content": system},
                                     {"role": "user", "content": untrusted(payload)}], schema, budget=budget)

    notes: list[str] = []
    # 1) ORCHESTRATOR
    try:
        plan = ask("report_orchestrator",
                   load_prompt("report_orchestrator", today=today.isoformat(),
                               sections="\n".join(f"- {k}: {h}" for k, h in SECTION_HELP.items())),
                   request, Plan)
    except Exception as e:  # noqa: BLE001 — never guess silently: defaults, and say so in notes
        log.warning("report orchestrator failed: %s: %s", type(e).__name__, e)
        plan = None
    keys, start, end, title_hint, plan_notes = checked_plan(plan, today)
    notes += plan_notes

    # 2) FACTS by code
    data = load_data(backend, ctx, start, end)
    facts = {k: compute_facts(k, data, backend, ctx, start, end, lang) for k in keys}

    def finish(title, summary, sections, rounds, quality, more=()):
        report = Report(title=title[:200], language=language, date_from=start, date_to=end, summary=summary[:2000],
                        sections=sections, rounds=rounds, quality=quality, notes=[*notes, *more][:20],
                        models=_models(made))
        return report.model_copy(update={"markdown": to_markdown(report)})

    def fallback(rounds, reason):
        title, summary, sections = template_report(keys, facts, lang, start, end, title_hint)
        return finish(title, summary, sections, rounds, "fallback", [reason])

    if not data["invoices"] and not data["payments"]:
        return fallback(0, "no invoices or payments in this period")

    try:
        # 3) WORKERS, in parallel
        def work(key):
            system = load_prompt("report_worker", section=key, section_help=SECTION_HELP[key], language=lang)
            return ask("report_worker", system, json.dumps(facts[key], ensure_ascii=False, default=str), SectionText)

        with ThreadPoolExecutor(max_workers=min(4, len(keys))) as pool:
            texts = list(pool.map(work, keys))
        # 4) SYNTHESIZER
        writer = load_prompt("report_writer", language=lang, date_from=start.isoformat(), date_to=end.isoformat())
        payload = {"title_hint": title_hint, "sections": [
            {"key": k, "heading": t.heading, "body": t.body, "facts": facts[k]} for k, t in zip(keys, texts, strict=True)]}
        draft = ask("report_writer", writer, json.dumps(payload, ensure_ascii=False, default=str), Draft)

        evaluator = load_prompt("report_evaluator", language=lang)
        feedback: list[str] = []
        for rounds in range(1, MAX_ROUNDS + 1):
            # 5) EVALUATOR: code first, then the LLM
            feedback = check_draft(draft, keys, facts, lang, start, end)
            numbers_ok = not feedback
            if numbers_ok:
                review = ask("report_evaluator", evaluator, json.dumps(
                    {"draft": draft.model_dump(), "facts": facts}, ensure_ascii=False, default=str), Review)
                if review.passes:
                    return finish(draft.title, draft.summary, _sections(draft, facts), rounds, "passed")
                feedback = review.feedback or ["the evaluator did not accept the draft"]
            if rounds == MAX_ROUNDS:
                break
            # 6) OPTIMIZER
            draft = ask("report_writer", writer, json.dumps({**draft.model_dump(), "facts": facts,
                                                             "reviewer_feedback": feedback},
                                                            ensure_ascii=False, default=str), Draft)
        if numbers_ok:
            return finish(draft.title, draft.summary, _sections(draft, facts), MAX_ROUNDS, "numbers_checked",
                          [f"evaluator feedback after {MAX_ROUNDS} rounds: {'; '.join(feedback)[:500]}"])
        return fallback(MAX_ROUNDS, f"the text never matched the data: {'; '.join(feedback)[:300]}")
    except BudgetExceeded as e:
        return fallback(0, f"stopped at the cost/time limit: {e}")
    except Exception as e:  # noqa: BLE001 — bad JSON twice, provider down, no key: the data report still goes out
        log.warning("report writing failed: %s: %s", type(e).__name__, e)
        return fallback(0, f"the report text could not be written ({type(e).__name__}); fixed wording used")


def _sections(draft: Draft, facts: dict) -> list[ReportSection]:
    return [ReportSection(key=s.key, heading=s.heading, body=s.body, facts=facts[s.key]) for s in draft.sections]


def _models(clients: list) -> dict[str, int]:
    total: dict[str, int] = defaultdict(int)
    for c in clients:
        for model, n in getattr(getattr(c, "usage", None), "models", {}).items():
            total[model] += n
    return dict(total)
