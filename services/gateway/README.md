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

## Policies

Rules live in the repo-root `policies/` folder, not in code:

- `defaults.yaml`: approval threshold, risk hold score, bank-change hold, fail mode, assistant limits
- `role_tools.yaml`: which tools each role may call (deny by default)

The gateway loads and validates both at start-up. A missing or unsafe file (for example
`creator_can_approve: true`, `fail_mode: allow`) stops the service instead of weakening the rules.
Set `POLICY_DIR` to point at a different folder.

## Risk service

`/v1/authorize` calls the risk service (`POST /v1/score`, sends `invoice_id`) for payment requests.

- Score >= `risk.hold_score` (70) -> `PENDING_APPROVAL`, reason "high risk score"
- Risk service down, slower than `gateway.timeout_ms`, or bad response -> `PENDING_APPROVAL`, reason "risk service unavailable" (fail closed, never ALLOW)
- Address: env `RISK_URL`. Default `http://risk:8000` (Docker). Local run without Docker: `RISK_URL=http://localhost:8003`