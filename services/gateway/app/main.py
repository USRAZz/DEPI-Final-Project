from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from securefin_contracts import (
    ApprovalRequest,
    ApprovalResult,
    AuditEvent,
    AuthorizeRequest,
    Decision,
    ExecuteCheckRequest,
    ExecuteCheckResult,
    GatewayDecision,
    ToolName,
)
from securefin_contracts.actions import CreatePaymentParams

from .approvals import ApprovalDenied, ApprovalKeyError, execute_check, load_hmac_key, submit_approval
from .audit_log import InMemoryAuditLog, PostgresAuditLog
from .db import build_engine
from .payments_client import PaymentNotFoundError, PaymentsUnavailableError, build_payments_client
from .policy import BASE_CURRENCY, get_policy
from .risk_client import RiskUnavailableError, build_risk_client
from .stores import DuplicateApprovalError, InMemoryApprovalStore, PostgresApprovalStore

app = FastAPI(title="SecureFin Security Gateway")

POLICY = get_policy()  # fails at start-up if policies/ is missing or invalid (fail closed)
RISK_CLIENT = build_risk_client(POLICY.defaults.gateway.timeout_ms)
PAYMENTS_CLIENT = build_payments_client(POLICY.defaults.gateway.timeout_ms)
# DATABASE_URL set -> the approvals and audit_log tables (migration 0001); otherwise in memory (local runs, tests).
ENGINE = build_engine()
APPROVAL_STORE = (PostgresApprovalStore(ENGINE, POLICY.defaults.approvals.approval_expiry_hours) if ENGINE
                  else InMemoryApprovalStore())
AUDIT_LOG = PostgresAuditLog(ENGINE) if ENGINE else InMemoryAuditLog()


def _audit(action: str, company_id: int | None, user_id: int | None, decision: str, result: str,
           parameters: dict) -> None:
    """Every approval / execute-check outcome is recorded (issue #16). Without a company there is no tenant
    chain to append to, and the request is refused anyway (approver company is required)."""
    if company_id is None:
        return
    AUDIT_LOG.append(AuditEvent(user_id=user_id, company_id=company_id, action=action, decision=decision,
                                result=result[:500], parameters=parameters, source_service="gateway",
                                tool_call=action))


@app.get("/health")
def health():
    return {"service": "gateway", "status": "ok"}


@app.post("/v1/authorize", response_model=GatewayDecision)
def authorize(req: AuthorizeRequest) -> GatewayDecision:
    passed: list[str] = []
    # 1. Identity & role allowlist
    if req.action.tool not in POLICY.tools_for(req.role):
        return GatewayDecision(decision=Decision.BLOCK, reasons=[f"role '{req.role.value}' may not call {req.action.tool.value}"])
    passed.append("role_allowlist")
    # 2. Parameter validation
    if req.action.tool == ToolName.CREATE_PAYMENT_REQUEST:
        try:
            params = CreatePaymentParams.model_validate(req.action.params)
        except ValidationError as e:
            return GatewayDecision(decision=Decision.BLOCK, reasons=[f"invalid parameters: {e.error_count()} error(s)"], checks_passed=passed)
        passed.append("param_validation")
        # 3. Approvals from policy
        approvers = POLICY.required_approvers(params.amount, params.currency)
        reasons: list[str] = []
        if params.currency != BASE_CURRENCY:
            reasons.append(f"currency {params.currency} is not {BASE_CURRENCY}: two approvers required")
        elif approvers == 2:
            reasons.append("amount above dual-approval threshold")
        # 4. Risk score — an unreachable or broken risk service holds the payment (never fails open)
        risk_score: float | None = None
        try:
            risk = RISK_CLIENT.score(params.invoice_id)
        except RiskUnavailableError:
            reasons.append("risk service unavailable: payment held for review")
        else:
            risk_score = risk.score
            passed.append("risk_check")
            if risk.score >= POLICY.defaults.risk.hold_score:
                reasons.append(f"high risk score {risk.score:g}: held for review")
        # TODO: maker-checker, HMAC
        if not reasons:
            reasons.append("all payment requests need one approval (stub policy)")
        return GatewayDecision(decision=Decision.PENDING_APPROVAL, reasons=reasons, checks_passed=passed,
                               risk_score=risk_score, required_approvers=approvers)
    return GatewayDecision(decision=Decision.ALLOW, checks_passed=passed)


def _load_payment(payment_request_id: int):
    try:
        return PAYMENTS_CLIENT.get(payment_request_id)
    except PaymentNotFoundError:
        raise HTTPException(status_code=404, detail=["payment request not found"]) from None
    except PaymentsUnavailableError:
        raise HTTPException(status_code=503, detail=["payment service unavailable: nothing approved"]) from None


def _signing_key() -> bytes:
    try:
        return load_hmac_key()
    except ApprovalKeyError:
        raise HTTPException(status_code=503, detail=["approval signing unavailable: nothing approved"]) from None


@app.post("/v1/approvals/{payment_request_id}", response_model=ApprovalResult)
def approve(payment_request_id: int, req: ApprovalRequest) -> ApprovalResult:
    params = {"payment_request_id": payment_request_id, "approve": req.approve}
    try:
        result = _approve(payment_request_id, req)
    except HTTPException as e:
        _audit("approval", req.company_id, req.approver_id, "BLOCK", f"{e.status_code}: {'; '.join(e.detail)}", params)
        raise
    # shortcut: the approval row and its audit entry are two transactions; an audit failure after a stored
    # approval returns 500 and leaves the approval without an entry. One shared transaction fixes it.
    _audit("approval", req.company_id, req.approver_id, result.status.value,
           "; ".join(result.reasons) or f"{result.approvals_received}/{result.approvals_required} approvals", params)
    return result


def _approve(payment_request_id: int, req: ApprovalRequest) -> ApprovalResult:
    if req.payment_request_id != payment_request_id:
        raise HTTPException(status_code=422, detail=["payment request id in path and body differ"])
    key = _signing_key()
    payment = _load_payment(payment_request_id)
    existing = APPROVAL_STORE.list(payment_request_id, company_id=payment.company_id)
    try:
        result, record = submit_approval(req, payment, existing, POLICY, key, datetime.now(UTC))
    except ApprovalDenied as e:
        raise HTTPException(status_code=403, detail=e.reasons) from None
    if record is not None:
        try:
            APPROVAL_STORE.add(record, company_id=payment.company_id)
        except DuplicateApprovalError:
            raise HTTPException(status_code=409, detail=["this approver has already decided"]) from None
    return result


@app.post("/v1/execute-check", response_model=ExecuteCheckResult)
def execute_check_endpoint(req: ExecuteCheckRequest) -> ExecuteCheckResult:
    """The api calls this right before executing a payment. Anything but allowed=true means do not pay."""
    params = {"payment_request_id": req.payment_request_id}
    try:
        key = _signing_key()
        payment = _load_payment(req.payment_request_id)
    except HTTPException as e:
        _audit("execute_check", req.company_id, req.requested_by, "BLOCK", f"{e.status_code}: {'; '.join(e.detail)}",
               params)
        raise
    result = execute_check(req, payment, APPROVAL_STORE.list(req.payment_request_id, company_id=payment.company_id),
                           POLICY, key, datetime.now(UTC))
    _audit("execute_check", req.company_id, req.requested_by, "ALLOW" if result.allowed else "BLOCK",
           "; ".join(result.reasons) or "allowed", params)
    return result
