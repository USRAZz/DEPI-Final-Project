# services/risk — Risk Engine (rules + ML + SHAP)

**Owner:** M4 (Ziad) · **Local port:** 8003

**Owns (only this service writes):** rules engine, models/ (artifacts via Git LFS or release assets), notebooks/, SHAP explanations

**Endpoints:** `/v1/score`

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
