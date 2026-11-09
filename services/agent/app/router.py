"""Routing: classify the user's request into one route (a single small LLM call)."""
import logging
from datetime import date
from enum import Enum

from pydantic import BaseModel, Field

from ai_core.llm import get_llm
from ai_core.prompts import load_prompt, untrusted

log = logging.getLogger(__name__)

class Route(str, Enum):
    invoice_upload = "invoice_upload"
    finance_question = "finance_question"
    payment_request = "payment_request"
    report_request = "report_request"
    unclear = "unclear"


# One place to add/change routes: the prompt is generated from this dict.
ROUTE_HELP = {
    Route.invoice_upload: "The user uploads, or wants to upload, a new invoice or receipt to be read.",
    Route.finance_question: "A question about existing invoices, spending, suppliers, alerts or policies.",
    Route.payment_request: "The user wants to pay, or prepare a payment for, an invoice or supplier.",
    Route.report_request: "The user wants a report or a summary document for a period.",
    Route.unclear: "Anything else, or not enough information to choose.",
}

FALLBACK_QUESTION = ("What would you like to do: upload an invoice, ask a finance question, "
                     "prepare a payment, or get a report?")


class RouteDecision(BaseModel):
    route: Route
    confidence: float = Field(ge=0, le=1)
    language: str = "en"
    clarifying_question: str | None = None


def route_request(message: str, *, has_attachment: bool = False, llm=None, min_confidence: float = 0.6) -> RouteDecision:
    if has_attachment and not message.strip():  # a file with no text is always an invoice: no LLM call needed
        return RouteDecision(route=Route.invoice_upload, confidence=1.0)

    llm = llm or get_llm("router")
    system = load_prompt(
        "router",
        routes="\n".join(f"- {r.value}: {h}" for r, h in ROUTE_HELP.items()),
        has_attachment=str(has_attachment).lower(),
        today=date.today().isoformat(),
    )
    try:
        d = llm.structured([{"role": "system", "content": system},
                            {"role": "user", "content": untrusted(message)}], RouteDecision)
    except Exception as e:  # provider down, bad JSON twice, ...: never guess, ask the user
        log.warning("router LLM call failed: %s: %s", type(e).__name__, e)
        return RouteDecision(route=Route.unclear, confidence=0.0, clarifying_question=FALLBACK_QUESTION)
    
    if d.route != Route.unclear and d.confidence < min_confidence:
        d = d.model_copy(update={"route": Route.unclear})
    if d.route == Route.unclear and not d.clarifying_question:
        d = d.model_copy(update={"clarifying_question": FALLBACK_QUESTION})
    return d