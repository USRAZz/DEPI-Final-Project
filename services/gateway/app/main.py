from fastapi import FastAPI
from pydantic import ValidationError
from securefin_contracts import AuthorizeRequest, Decision, GatewayDecision, ToolName
from securefin_contracts.actions import CreatePaymentParams

from .audit_chain import compute_hash  # noqa: F401  (used by the real audit endpoint)
from .policy import BASE_CURRENCY, get_policy
from .risk_client import RiskUnavailableError, build_risk_client

app = FastAPI(title="SecureFin Security Gateway")

POLICY = get_policy()  # fails at start-up if policies/ is missing or invalid (fail closed)
RISK_CLIENT = build_risk_client(POLICY.defaults.gateway.timeout_ms)


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
