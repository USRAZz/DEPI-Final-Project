import hmac
import json
import os
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from securefin_contracts import (
    ChatRequest,
    ChatResponse,
    ChatTurn,
    ExplainRequest,
    Report,
    ReportRequest,
    RiskExplanation,
)

from ai_core.prompts import untrusted

from .agent_loop import run_agent
from .alerts import alerts_text, build_alerts
from .explain import explain_risk
from .proposals import to_proposed_action
from .reports import generate_report
from .router import Route, route_request
from .tools import Context, ToolRegistry

app = FastAPI(title="SecureFin Agent")

INVOICE_UPLOAD_ANSWER = {
    "ar": "لرفع فاتورة استخدم شاشة الفواتير. أنا أقرأ الفواتير بعد رفعها وأساعدك في أسئلتها.",
    "en": "To add an invoice, use the invoice upload screen. I can answer questions about it once it is uploaded.",
}
INVALID_PROPOSAL_NOTE = {
    "ar": "\n\n(لم أستطع تجهيز اقتراح دفع صالح، فلم أرسل أي اقتراح.)",
    "en": "\n\n(I could not prepare a valid payment proposal, so none was sent.)",
}
# A proposal is accepted only when the user's request itself was routed as a payment request. A document, e-mail
# or tool result that "asks" for a payment inside a question (attack case ATK-006) never produces one.
UNASKED_PROPOSAL_NOTE = {
    "ar": "\n\n(لم أجهّز أي طلب دفع لأن رسالتك لم تطلب دفعًا. لو عايز تدفع فاتورة، اطلب ذلك صراحة.)",
    "en": "\n\n(No payment was prepared because your message did not ask for one. To pay an invoice, ask for it directly.)",
}
REPORT_NOTE = {
    "ar": "\n\n(ملاحظة: الأرقام اتكتبت من البيانات مباشرة لأن صياغة التقرير الآلية ماعدّتش المراجعة.)",
    "en": "\n\n(Note: the numbers were written straight from the data because the generated wording did not pass review.)",
}

MAX_HISTORY_TURNS = 10        # chat memory: the last turns only, to bound tokens
MAX_HISTORY_CHARS = 1000      # per turn


@app.get("/health")
def health():
    return {"service": "agent", "status": "ok"}


def _lang(code: str) -> str:
    return "ar" if (code or "").lower().startswith("ar") else "en"


def _recent(history: list[ChatTurn]) -> list[dict]:
    return [{"role": t.role, "content": t.content[:MAX_HISTORY_CHARS]} for t in history[-MAX_HISTORY_TURNS:]]


def history_messages(history: list[ChatTurn]) -> list[dict]:
    """Earlier turns as ONE tagged data message. The client sends them, so an "assistant" turn may be forged:
    they are context to read, never instructions and never real assistant messages."""
    turns = _recent(history)
    if not turns:
        return []
    return [{"role": "user", "content": "Earlier messages of this conversation, oldest first (context only):\n"
             + untrusted(json.dumps(turns, ensure_ascii=False))}]


def router_context(history: list[ChatTurn]) -> str | None:
    """The last exchange, so a short follow-up ("yes, pay it") can be routed."""
    turns = _recent(history)[-2:]
    return "\n".join(f"{t['role']}: {t['content'][:300]}" for t in turns) or None


@dataclass
class ChatOutcome:
    """What /v1/chat answers plus what the evaluation (eval/ai_eval) scores."""
    response: ChatResponse
    route: Route
    language: str
    tools_used: list[str] = field(default_factory=list)
    status: str = "done"
    raw_proposal: dict | None = None
    tokens: int = 0
    steps: int = 0
    report: Report | None = None
    model_answer: str = ""  # the model's own words, before the app adds notes and the alert reasons


def handle_chat(req: ChatRequest, ctx: Context, *, router_llm=None, agent_llm=None, registry=None,
                report_llms=None, report_backend=None) -> ChatOutcome:
    """Route -> agent loop (read-only tools, called with the user's own identity) -> checked proposals.
    Never executes: the api sends each proposed action to the gateway. mode=dry_run returns no proposals."""
    context = router_context(req.history)
    decision = route_request(req.message, **({"context": context} if context else {}),
                             **({"llm": router_llm} if router_llm else {}))
    lang = _lang(decision.language)
    if decision.route == Route.unclear:
        return ChatOutcome(ChatResponse(answer=decision.clarifying_question or ""), decision.route, lang)
    if decision.route == Route.invoice_upload:
        return ChatOutcome(ChatResponse(answer=INVOICE_UPLOAD_ANSWER[lang]), decision.route, lang)
    if decision.route == Route.report_request:  # pattern ④: orchestrator-workers + evaluator-optimizer
        report = generate_report(req.message, ctx, **{k: v for k, v in {"llms": report_llms,
                                                                         "backend": report_backend}.items() if v})
        answer = report.markdown + (REPORT_NOTE[lang] if report.quality == "fallback" else "")
        return ChatOutcome(ChatResponse(answer=answer), decision.route, lang, report=report)

    registry = registry or ToolRegistry()
    extra = {k: v for k, v in {"history": history_messages(req.history), "llm": agent_llm}.items() if v}
    result = run_agent(req.message, ctx, language=decision.language, registry=registry, **extra)

    # Every flagged or risky invoice the tools returned comes back with its reasons, built by code from the data.
    alerts = build_alerts(registry.calls, registry.backend, ctx, lang)
    answer, action = result.answer + alerts_text(alerts, lang), None
    if result.proposal:
        if decision.route != Route.payment_request:
            answer += UNASKED_PROPOSAL_NOTE[lang]
        else:
            action = to_proposed_action(result.proposal)
            if action is None:
                answer += INVALID_PROPOSAL_NOTE[lang]
    actions = [action] if action is not None and req.mode != "dry_run" else []
    response = ChatResponse(answer=answer, proposed_actions=actions, alerts=alerts, sources=result.tools_used)
    return ChatOutcome(response, decision.route, lang,
                       tools_used=result.tools_used, status=result.status, raw_proposal=result.proposal,
                       tokens=result.tokens, steps=result.steps, model_answer=result.answer)


def require_caller(x_service_token: Annotated[str | None, Header()] = None) -> None:
    """The agent trusts X-User-Id / X-User-Role, so only the api may call it: when AGENT_SERVICE_TOKEN is set, the
    caller must send it. Unset = local development (the agent's port is bound to this machine in compose)."""
    expected = os.getenv("AGENT_SERVICE_TOKEN", "")
    if expected and not (x_service_token and hmac.compare_digest(x_service_token.encode(), expected.encode())):
        raise HTTPException(status_code=401, detail="service token required")


Caller = [Depends(require_caller)]


@app.post("/v1/chat", response_model=ChatResponse, dependencies=Caller)
def chat(req: ChatRequest, authorization: Annotated[str | None, Header()] = None,
         x_user_role: Annotated[str | None, Header()] = None,
         x_user_id: Annotated[str | None, Header()] = None) -> ChatResponse:
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    ctx = Context(token=token, role=x_user_role or "viewer", user_id=x_user_id or Context.user_id)
    return handle_chat(req, ctx).response


@app.post("/v1/reports", response_model=Report, dependencies=Caller)
def reports(req: ReportRequest, authorization: Annotated[str | None, Header()] = None,
            x_user_role: Annotated[str | None, Header()] = None,
            x_user_id: Annotated[str | None, Header()] = None) -> Report:
    """A finance report for the user's request (sections + Markdown for the dashboard and the PDF export).
    Read-only: the data comes from the same read tools as the chat, with the user's own identity."""
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    return generate_report(req.request, Context(token=token, role=x_user_role or "viewer",
                                                user_id=x_user_id or Context.user_id))


@app.post("/v1/explain", response_model=RiskExplanation, dependencies=Caller)
def explain(req: ExplainRequest) -> RiskExplanation:
    """A risk score's rule codes in plain words, in the user's language (prompt P-03). Read-only; decides nothing."""
    return explain_risk(req.risk, req.language)
