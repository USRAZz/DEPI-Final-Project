from typing import Annotated

from fastapi import FastAPI, Header
from securefin_contracts import ChatRequest, ChatResponse

from .agent_loop import run_agent
from .proposals import to_proposed_action
from .router import Route, route_request
from .tools import Context

app = FastAPI(title="SecureFin Agent")

INVOICE_UPLOAD_ANSWER = {
    "ar": "لرفع فاتورة استخدم شاشة الفواتير. أنا أقرأ الفواتير بعد رفعها وأساعدك في أسئلتها.",
    "en": "To add an invoice, use the invoice upload screen. I can answer questions about it once it is uploaded.",
}
INVALID_PROPOSAL_NOTE = {
    "ar": "\n\n(لم أستطع تجهيز اقتراح دفع صالح، فلم أرسل أي اقتراح.)",
    "en": "\n\n(I could not prepare a valid payment proposal, so none was sent.)",
}


@app.get("/health")
def health():
    return {"service": "agent", "status": "ok"}


def _lang(code: str) -> str:
    return "ar" if (code or "").lower().startswith("ar") else "en"


@app.post("/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest, authorization: Annotated[str | None, Header()] = None,
         x_user_role: Annotated[str | None, Header()] = None) -> ChatResponse:
    """Route -> agent loop (read-only tools, called with the user's own token) -> proposed actions.
    Never executes: the api sends each proposed action to the gateway. mode=dry_run returns no proposals."""
    decision = route_request(req.message)
    lang = _lang(decision.language)
    if decision.route == Route.unclear:
        return ChatResponse(answer=decision.clarifying_question or "")
    if decision.route == Route.invoice_upload:
        return ChatResponse(answer=INVOICE_UPLOAD_ANSWER[lang])

    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    ctx = Context(token=token, role=x_user_role or "viewer")
    result = run_agent(req.message, ctx, language=decision.language)

    action = to_proposed_action(result.proposal)
    answer = result.answer
    if result.proposal and action is None:
        answer += INVALID_PROPOSAL_NOTE[lang]
    actions = [action] if action is not None and req.mode != "dry_run" else []
    return ChatResponse(answer=answer, proposed_actions=actions)
