from fastapi import FastAPI
from securefin_contracts import AuthorizeRequest, Decision, ProposedAction, Role

from .clients import gateway_authorize

app = FastAPI(title="SecureFin API")


@app.get("/health")
def health():
    return {"service": "api", "status": "ok"}


@app.post("/payments/propose")
async def propose_payment(action: ProposedAction):
    """Skeleton path: agent proposal -> gateway decision -> execute only on ALLOW. (Auth is stubbed.)"""
    req = AuthorizeRequest(user_id=1, role=Role.ACCOUNTANT, company_id=1, action=action, request_id="demo-1")
    decision = await gateway_authorize(req)
    executed = decision.decision == Decision.ALLOW  # TODO(Karim): real simulated executor + HMAC re-check
    return {"decision": decision.model_dump(), "executed": executed}
