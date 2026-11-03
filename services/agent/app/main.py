from fastapi import FastAPI
from securefin_contracts import ChatRequest, ChatResponse, ProposedAction, ToolName

app = FastAPI(title="SecureFin Agent")


@app.get("/health")
def health():
    return {"service": "agent", "status": "ok"}


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """STUB. Real version: LangGraph plan -> tools via api (user JWT) -> ProposedAction list. Never executes."""
    action = ProposedAction(tool=ToolName.CREATE_PAYMENT_REQUEST,
                            params={"invoice_id": 1, "vendor_id": 1, "amount": "1500", "currency": "EGP"},
                            rationale="stub")
    return ChatResponse(answer="(stub) I propose a payment request for invoice 1.", proposed_actions=[action])
