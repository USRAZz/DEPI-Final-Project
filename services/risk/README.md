# services/risk — Risk Engine (rules now; ML/SHAP later)

**Owner:** M4 (Ziad) · **Local port:** 8003

**Owns (only this service writes):** rules engine, models/ (artifacts via Git LFS or release assets), notebooks/, SHAP explanations

**Endpoints:** `/v1/score` (rules-only MVP implementation)

## Current scoring behavior
The endpoint scores only explicitly supplied `features` and returns stable rule codes. Supported input keys:

| Feature | Trigger | Demo points |
| --- | --- | ---: |
| `duplicate_detected: true` | Suspected duplicate invoice | 70 |
| `bank_account_mismatch: true` | Vendor account mismatch | 70 |
| `vendor_change_pending: true` | Vendor bank change awaiting verification | 50 |
| `invoice_total_mismatch: true` | Invoice arithmetic mismatch | 40 |
| `invoice_total_egp: number` | At or above `RISK_AMOUNT_REVIEW_EGP` (default 100,000) | 20 |
| `ocr_confidence: number` | Below 0.65 | 15 |

Points are capped at 100. `RISK_MEDIUM_THRESHOLD` (default 30) and `RISK_HIGH_THRESHOLD` (default 70) determine the returned level. Rule weights and thresholds are provisional demo settings, not approved financial policy. A risk score is advisory: the gateway owns allow/hold/block decisions. Do not send bank account values or other raw sensitive data as rule explanations. `shap_reasons` remains empty until a model and explainability workflow are implemented.

The feature keys are currently an implementation convention, not yet part of the shared typed contract. Coordinate with the contract owners before other services depend on them.

## Run alone
```bash
cd services/risk
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ../../contracts -r requirements-dev.txt
uvicorn app.main:app --reload --port 8003
pytest
```

## Rules
- Import shared types from `securefin_contracts` — never redefine them here.
- Need data owned by another service? Call its endpoint; do not write its tables.
- Document every new endpoint in this README.
