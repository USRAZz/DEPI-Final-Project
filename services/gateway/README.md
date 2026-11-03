# services/gateway — AI Security Gateway (deterministic, no LLM)

**Owner:** M3 (Anan) · **Local port:** 8002

**Owns (only this service writes):** repo-root `policies/*.yaml`, approvals, vendor_change_requests, audit_log (the ONLY writer) + chain verifier

**Endpoints:** `/v1/authorize`, `/v1/approvals/{id}`, `/v1/vendor-changes/*`, `/v1/audit/events`, `/v1/audit/verify`

## Run alone
```bash
cd services/gateway
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ../../contracts -r requirements-dev.txt
uvicorn app.main:app --reload --port 8002
pytest
```

## Rules
- Import shared types from `securefin_contracts` — never redefine them here.
- Need data owned by another service? Call its endpoint; do not write its tables.
- Document every new endpoint in this README.

Policies live in the repo-root `policies/` folder (one source for the gateway and the stretch RAG, SDD §7).
