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

## Approvals

`app/approvals.py` holds the approval rules as pure functions (no database, no web framework):

- **Maker-checker:** the creator of a payment request can never approve it
- Only roles in `approvals.approver_roles` (policy) may approve; company must match
- One person decides once; any rejection stops the request
- 1 approver, or 2 distinct approvers above EGP 10,000 or for any non-EGP amount
- Every approval is signed (HMAC-SHA256) over the exact payment details (company, invoice, vendor, amount, currency) and the decision
- Approvals and the payment request expire after `approvals.approval_expiry_hours` (72)
- `execute_check` recomputes every signature from the current payment data; any change after approval means "not allowed"

Signing key: env `APPROVAL_HMAC_KEY`, at least 32 bytes, never in Git. Generate one with
`python -c "import secrets; print(secrets.token_hex(32))"`.
The HTTP endpoints and the `approvals` table are added in the next PR.

## Approval endpoints

| Endpoint | Body | Returns |
|---|---|---|
| `POST /v1/approvals/{payment_request_id}` | `ApprovalRequest` (must include `approver_role` and `company_id`, set by the api from the session) | `ApprovalResult` |
| `POST /v1/execute-check` | `ExecuteCheckRequest` | `ExecuteCheckResult` |

- `/v1/approvals`: refused with **403** and a list of reasons (maker-checker, wrong role, wrong company, already decided, already rejected, not awaiting approval). Nothing is stored when refused.
- `/v1/execute-check`: the api **must call this right before executing a payment**. Pay only if `allowed` is `true`.
- **404** unknown payment request; **503** if the api is unreachable or `APPROVAL_HMAC_KEY` is missing or short (nothing is approved).
- The gateway reads the payment request from the api: `GET {API_URL}/payments/{id}` returning `PaymentRequestInfo`.
  `API_URL` defaults to `http://api:8000` (Docker); outside Docker use `http://localhost:8000`.
- Approvals are kept in memory for now (lost on restart). The database-backed store follows once the `approvals` table migration exists.

## Storage and audit (issues #15, #16)

- `DATABASE_URL` set: approvals go to the `approvals` table and every approval / execute-check outcome (including
  refusals and 403/404/503) is appended to `audit_log`, both through role `securefin_gateway` with `app.company_id`
  set (row-level security). Without `DATABASE_URL` both live in memory (local runs, unit tests).
- `audit_log` is one hash chain per company (`app/audit_log.py`); `verify(company_id)` returns the first broken
  entry or None. Appends take a per-company advisory lock so two requests cannot fork the chain.
- Known shortcut: an approval row and its audit entry are written in two transactions.
- Tests: `tests/test_audit_log.py`; `tests/test_db_store_audit.py` needs `TEST_DATABASE_URL` (CI job `migrations-postgres`).
