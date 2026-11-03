from fastapi import FastAPI
from securefin_contracts import RiskLevel, RiskRequest, RiskScore

app = FastAPI(title="SecureFin Risk Engine")


@app.get("/health")
def health():
    return {"service": "risk", "status": "ok"}


@app.post("/v1/score", response_model=RiskScore)
def score(req: RiskRequest) -> RiskScore:
    """STUB. Real version: rule hits + Isolation Forest/XGBoost score + top-3 SHAP reasons."""
    return RiskScore(score=10, level=RiskLevel.LOW, rule_hits=[], model_version="stub")
