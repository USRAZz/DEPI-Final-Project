"""Explainable, rules-only risk scoring for the MVP skeleton."""

import os

from fastapi import FastAPI
from securefin_contracts import RiskLevel, RiskRequest, RiskScore

app = FastAPI(title="SecureFin Risk Engine")

# These are demo defaults, not approved financial policy. The gateway owns
# payment decisions; this service only reports a risk score and rule codes.
_HIGH_THRESHOLD = float(os.getenv("RISK_HIGH_THRESHOLD", "70"))
_MEDIUM_THRESHOLD = float(os.getenv("RISK_MEDIUM_THRESHOLD", "30"))
_AMOUNT_REVIEW_EGP = float(os.getenv("RISK_AMOUNT_REVIEW_EGP", "100000"))


@app.get("/health")
def health():
    return {"service": "risk", "status": "ok"}


@app.post("/v1/score", response_model=RiskScore)
def score(req: RiskRequest) -> RiskScore:
    """Score explicitly supplied features; never return sensitive feature values."""
    features = req.features
    points = 0
    hits: list[str] = []

    def flag(feature: str, code: str, weight: int) -> None:
        nonlocal points
        if features.get(feature) is True:
            hits.append(code)
            points += weight

    flag("duplicate_detected", "DUPLICATE_INVOICE", 70)
    flag("bank_account_mismatch", "VENDOR_ACCOUNT_MISMATCH", 70)
    flag("vendor_change_pending", "VENDOR_BANK_CHANGE_PENDING", 50)
    flag("invoice_total_mismatch", "INVOICE_TOTAL_MISMATCH", 40)

    amount = features.get("invoice_total_egp")
    if isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount >= _AMOUNT_REVIEW_EGP:
        hits.append("HIGH_VALUE_REVIEW")
        points += 20

    confidence = features.get("ocr_confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and confidence < 0.65:
        hits.append("LOW_OCR_CONFIDENCE")
        points += 15

    risk_score = float(min(points, 100))
    if risk_score >= _HIGH_THRESHOLD:
        level = RiskLevel.HIGH
    elif risk_score >= _MEDIUM_THRESHOLD:
        level = RiskLevel.MEDIUM
    else:
        level = RiskLevel.LOW

    return RiskScore(
        score=risk_score,
        level=level,
        rule_hits=hits,
        shap_reasons=[],
        model_version="rules-demo-v1",
    )
