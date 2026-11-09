from fastapi import FastAPI
from pydantic import ValidationError
from securefin_contracts import AuthorizeRequest, Decision, GatewayDecision, ToolName
from securefin_contracts.actions import CreatePaymentParams

from .audit_chain import compute_hash  # noqa: F401  (used by the real audit endpoint)
from .policy import BASE_CURRENCY, get_policy

app = FastAPI(title="SecureFin Security Gateway")

POLICY = get_policy()  # fails at start-up if policies/ is missing or invalid (fail closed)


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
        # 3. Approvals from policy — TODO: risk score from risk service, maker-checker, HMAC
        approvers = POLICY.required_approvers(params.amount, params.currency)
        if params.currency != BASE_CURRENCY:
            reason = f"currency {params.currency} is not {BASE_CURRENCY}: two approvers required"
        elif approvers == 2:
            reason = "amount above dual-approval threshold"
        else:
            reason = "all payment requests need one approval (stub policy)"
        return GatewayDecision(decision=Decision.PENDING_APPROVAL, reasons=[reason],
                               checks_passed=passed, required_approvers=approvers)
    return GatewayDecision(decision=Decision.ALLOW, checks_passed=passed)
