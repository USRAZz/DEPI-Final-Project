"""What the assistant needs from the api (services/agent, Yousra).

Read endpoints for the agent's tools, called with the user's own identity (the agent forwards it), so the user's
company and role always apply:
    GET /invoices?vendor_name=&status=&date_from=&date_to=&limit=   -> list of invoice rows
    GET /transactions?date_from=&date_to=                            -> paid payment requests
    GET /invoices/{id}/risk                                          -> the stored risk score of the invoice's payment

And the screens' way to the agent (the browser never calls the agent directly):
    POST /chat     ChatRequest   -> ChatResponse   (agent POST /v1/chat)
    POST /reports  ReportRequest -> Report         (agent POST /v1/reports)
The user's id and role are taken from the session and sent to the agent; the request body cannot choose them.
"""
import os
from datetime import date

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import ValidationError
from securefin_contracts import ChatRequest, ChatResponse, Invoice, InvoiceStatus, Report, ReportRequest

from .deps import StoreDep, UserDep
from .models import PaymentRecord

router = APIRouter()

AGENT_URL = os.getenv("AGENT_URL", "http://agent:8000")  # docker service name; http://localhost:8001 outside Docker
MAX_ROWS = 200


# ------------------------------------------------------------------------------------------- read endpoints

def _invoice_date(inv: Invoice) -> date:
    return inv.fields.date if inv.fields is not None else inv.created_at.date()


def _invoice_row(inv: Invoice, vendors: dict[int, str], amounts: dict[int, PaymentRecord]) -> dict:
    """The shape the agent's tools read (the same keys as its MockBackend)."""
    request = amounts.get(inv.id)
    amount = inv.fields.amount if inv.fields is not None else (request.amount if request else None)
    currency = inv.fields.currency if inv.fields is not None else (request.currency if request else "EGP")
    return {"id": inv.id, "vendor_id": inv.vendor_id, "vendor_name": vendors.get(inv.vendor_id or 0),
            "invoice_number": inv.fields.invoice_no if inv.fields is not None else None,
            "invoice_date": _invoice_date(inv).isoformat(),
            "total_amount": float(amount) if amount is not None else None, "currency": currency,
            "status": inv.status.value, "category": inv.category, "extraction_issues": list(inv.extraction_issues),
            "duplicate_of": inv.duplicate_of}


def _vendor_names(store, company_id: int, ids) -> dict[int, str]:
    names = {}
    for vid in {i for i in ids if i}:
        vendor = store.vendor(vid, company_id)
        if vendor is not None:
            names[vid] = vendor.name
    return names


@router.get("/invoices")
def list_invoices(user: UserDep, store: StoreDep, vendor_name: str | None = None, status_: str | None = Query(None, alias="status"),
                  date_from: date | None = None, date_to: date | None = None,
                  limit: int = Query(50, ge=1, le=MAX_ROWS)) -> list[dict]:
    """The company's invoices, newest first. status = an InvoiceStatus value (FLAGGED, VALIDATED, ...)."""
    invoices = store.company_invoices(user.company_id)
    requests = {p.invoice_id: p for p in store.company_requests(user.company_id)}
    vendors = _vendor_names(store, user.company_id, (i.vendor_id for i in invoices))
    rows = []
    for inv in invoices:
        d = _invoice_date(inv)
        if date_from and d < date_from or date_to and d > date_to:
            continue
        if status_ and inv.status.value.upper() != status_.strip().upper():
            continue
        row = _invoice_row(inv, vendors, requests)
        if vendor_name and vendor_name.strip().lower() not in (row["vendor_name"] or "").lower():
            continue
        rows.append(row)
    rows.sort(key=lambda r: (r["invoice_date"], r["id"]), reverse=True)
    return rows[:limit]


@router.get("/transactions")
def list_transactions(user: UserDep, store: StoreDep, date_from: date | None = None,
                      date_to: date | None = None) -> list[dict]:
    """Paid (simulated) payment requests. `date` is the request's date: payments carry no separate paid-at time yet."""
    paid = [p for p in store.company_requests(user.company_id) if p.status == InvoiceStatus.PAID_SIMULATED]
    vendors = _vendor_names(store, user.company_id, (p.vendor_id for p in paid))
    rows = []
    for p in paid:
        d = p.created_at.date()
        if date_from and d < date_from or date_to and d > date_to:
            continue
        rows.append({"date": d.isoformat(), "payment_request_id": p.id, "invoice_id": p.invoice_id,
                     "vendor_name": vendors.get(p.vendor_id), "amount": float(p.amount), "currency": p.currency,
                     "status": "paid"})
    return sorted(rows, key=lambda r: r["date"], reverse=True)[:MAX_ROWS]


@router.get("/invoices/{invoice_id}/risk")
def invoice_risk(invoice_id: int, user: UserDep, store: StoreDep) -> dict:
    """The risk score stored for the payment request of this invoice. scored=false when it has none yet."""
    if store.invoice(invoice_id, user.company_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")
    for request in sorted(store.company_requests(user.company_id), key=lambda p: p.created_at, reverse=True):
        if request.invoice_id == invoice_id and (risk := store.risk(request.id)) is not None:
            return {"invoice_id": invoice_id, "scored": True, "payment_request_id": request.id,
                    **risk.model_dump(mode="json")}
    return {"invoice_id": invoice_id, "scored": False, "score": None, "level": None, "rule_hits": []}


# ------------------------------------------------------------------------------------------- to the agent

def _agent_call(path: str, body: dict, user) -> httpx.Response:
    headers = {"X-User-Id": str(user.id), "X-User-Role": user.role.value}
    if token := os.getenv("AGENT_SERVICE_TOKEN", ""):
        headers["X-Service-Token"] = token
    try:
        resp = httpx.post(f"{os.getenv('AGENT_URL', AGENT_URL)}{path}", json=body, headers=headers,
                          timeout=float(os.getenv("AGENT_TIMEOUT_S", "180")))
    except httpx.HTTPError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "assistant unavailable") from None
    if resp.status_code != 200:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"assistant unavailable (HTTP {resp.status_code})")
    return resp


@router.post("/chat")
def chat(req: ChatRequest, user: UserDep) -> ChatResponse:
    """The assistant. It only proposes: a proposed payment still goes through POST /payments/propose and the gateway."""
    resp = _agent_call("/v1/chat", req.model_dump(mode="json"), user)
    try:
        return ChatResponse.model_validate_json(resp.content)
    except ValidationError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "assistant answered something unreadable") from None


@router.post("/reports")
def report(req: ReportRequest, user: UserDep) -> Report:
    resp = _agent_call("/v1/reports", req.model_dump(mode="json"), user)
    try:
        return Report.model_validate_json(resp.content)
    except ValidationError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "assistant answered something unreadable") from None
