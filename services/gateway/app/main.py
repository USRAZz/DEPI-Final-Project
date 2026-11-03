from fastapi import FastAPI
from pydantic import ValidationError
from securefin_contracts import AuthorizeRequest, Decision, GatewayDecision, Role, ToolName
from securefin_contracts.actions import CreatePaymentParams

from .audit_chain import compute_hash  # noqa: F401  (used by the real audit endpoint)

app = FastAPI(title="SecureFin Security Gateway")

# TODO(Anan): load from policies/role_tools.yaml instead of hard-coding
ROLE_ALLOWLIST: dict[Role, set[ToolName]] = {
    Role.VIEWER: {ToolName.GET_INVOICES, ToolName.GET_TRANSACTIONS, ToolName.GENERATE_REPORT},
    Role.ACCOUNTANT: {ToolName.GET_INVOICES, ToolName.GET_TRANSACTIONS, ToolName.CHECK_DUPLICATE,
                      ToolName.GET_RISK_SCORE, ToolName.CREATE_PAYMENT_REQUEST, ToolName.GENERATE_REPORT},
    Role.APPROVER: {ToolName.GET_INVOICES, ToolName.GET_TRANSACTIONS, ToolName.GET_RISK_SCORE, ToolName.GENERATE_REPORT},
    Role.ADMIN: set(ToolName),
}
DUAL_APPROVAL_THRESHOLD = 10_000  # EGP (assumption from Proposal v2 — move to policy YAML)


@app.get("/health")
def health():
    return {"service": "gateway", "status": "ok"}


@app.post("/v1/authorize", response_model=GatewayDecision)
def authorize(req: AuthorizeRequest) -> GatewayDecision:
    passed: list[str] = []
    # 1. Identity & role allowlist
    if req.action.tool not in ROLE_ALLOWLIST.get(req.role, set()):
        return GatewayDecision(decision=Decision.BLOCK, reasons=[f"role '{req.role.value}' may not call {req.action.tool.value}"])
    passed.append("role_allowlist")
    # 2. Parameter validation
    if req.action.tool == ToolName.CREATE_PAYMENT_REQUEST:
        try:
            params = CreatePaymentParams.model_validate(req.action.params)
        except ValidationError as e:
            return GatewayDecision(decision=Decision.BLOCK, reasons=[f"invalid parameters: {e.error_count()} error(s)"], checks_passed=passed)
        passed.append("param_validation")
        # 3. Policy (stub) — TODO: policy YAML engine, risk score from risk service, maker-checker, HMAC
        if params.amount > DUAL_APPROVAL_THRESHOLD:
            return GatewayDecision(decision=Decision.PENDING_APPROVAL, reasons=["amount above dual-approval threshold"],
                                   checks_passed=passed, required_approvers=2)
        return GatewayDecision(decision=Decision.PENDING_APPROVAL, reasons=["all payment requests need one approval (stub policy)"],
                               checks_passed=passed, required_approvers=1)
    return GatewayDecision(decision=Decision.ALLOW, checks_passed=passed)
