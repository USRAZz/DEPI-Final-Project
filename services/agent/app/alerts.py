"""Every flagged or risky invoice the assistant used comes back WITH its reasons (ChatResponse.alerts).

Built by code from what the read-only tools returned in this turn, never from the model's text: the user always sees
why an invoice is suspicious (duplicate, wrong total, account changed, hidden instructions, ...) even if the model
forgot to say it. A flagged invoice the model listed but did not score is scored here (one more read-only call).
"""
from securefin_contracts import InvoiceAlert, RiskLevel, RiskReason

from .explain import LEVEL_WORDS, meaning, no_code_reason

MAX_ALERTS = 10
_LEVELS = {lvl.value for lvl in RiskLevel}


def _is_problem(invoice: dict) -> bool:
    return (str(invoice.get("status", "")).upper() in ("FLAGGED", "NEEDS-REVIEW", "VENDOR_CHANGE_PENDING")
            or bool(invoice.get("extraction_issues")) or invoice.get("duplicate_of") is not None)


def _risky(risk: dict) -> bool:
    return bool(risk.get("rule_hits")) or str(risk.get("level") or "low").lower() in ("medium", "high")


def build_alerts(calls: list[tuple[str, dict, object]], backend, ctx, lang: str) -> list[InvoiceAlert]:
    invoices: dict[int, dict] = {}
    risks: dict[int, dict] = {}
    for name, args, result in calls:
        if name == "get_invoices" and isinstance(result, list):
            for inv in result:
                if isinstance(inv, dict) and isinstance(inv.get("id"), int):
                    invoices.setdefault(inv["id"], inv)
        elif name == "get_risk_score" and isinstance(result, dict):
            try:
                risks[int(args.get("invoice_id"))] = result
            except (TypeError, ValueError):
                continue

    wanted = [i for i, inv in invoices.items() if _is_problem(inv)] + [i for i, r in risks.items() if _risky(r)]
    alerts = []
    for invoice_id in list(dict.fromkeys(wanted))[:MAX_ALERTS]:
        inv = invoices.get(invoice_id, {})
        risk = risks.get(invoice_id)
        if risk is None and backend is not None:
            try:
                risk = backend.get_risk_score(ctx, invoice_id) or {}
            except Exception:  # noqa: BLE001 — the alert still goes out with the invoice's own codes
                risk = {}
        risk = risk or {}
        codes = list(dict.fromkeys([*risk.get("rule_hits", []), *inv.get("extraction_issues", [])]))
        level = str(risk.get("level") or "").lower()
        reasons = [RiskReason(code=c, text=meaning(c, lang)) for c in codes]
        if not reasons:
            code = "RISK_LEVEL" if level in ("medium", "high") else "FLAGGED"
            reasons = [RiskReason(code=code, text=no_code_reason(level, lang))]
        alerts.append(InvoiceAlert(
            invoice_id=invoice_id, invoice_number=inv.get("invoice_number"), vendor=inv.get("vendor_name"),
            status=inv.get("status"), level=RiskLevel(level) if level in _LEVELS else None,
            score=risk.get("score") if isinstance(risk.get("score"), (int, float)) else None, reasons=reasons))
    return alerts


def alerts_text(alerts: list[InvoiceAlert], lang: str) -> str:
    """The reasons as a short block under the answer, in the user's language."""
    if not alerts:
        return ""
    ar = lang == "ar"
    lines = ["", "", "سبب التنبيهات:" if ar else "Why these invoices have alerts:"]
    for a in alerts:
        name = f"{'فاتورة' if ar else 'Invoice'} {a.invoice_number or a.invoice_id}"
        if a.vendor:
            name += f" ({a.vendor})"
        if a.level is not None:
            name += f" — {LEVEL_WORDS[a.level.value][lang]}"
            if a.score is not None:
                name += f" ({a.score:g}/100)"
        lines.append(f"- {name}:")
        lines += [f"  • {r.text}" for r in a.reasons]
    return "\n".join(lines)
