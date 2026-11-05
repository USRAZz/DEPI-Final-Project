# services/api — Platform & Integration API

**Owner:** M1 (Karim) · **Local port:** 8000

**Owns (only this service writes):** users, roles, role_tools, vendors, invoices, transactions, payment_requests, Alembic migrations, JWT auth, rate limiting, simulated payment executor

**Planned endpoints:** `/auth/login`, `/invoices/upload`, `/invoices`, `/chat` (proxy to agent), `/payments`, `/reports`

## Run alone
```bash
cd services/api
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ../../contracts -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
pytest
```

API docs: http://localhost:8000/docs

## Endpoints available now

The frontend reaches these under `/api`; the dev proxy removes that prefix.

| Method | Path | |
|---|---|---|
| GET | `/health` | |
| POST | `/payments/propose` | Agent proposal → gateway decision (auth stubbed) |
| GET | `/me` | Signed-in user |
| GET | `/dashboard` | Totals and payments awaiting approval |
| GET | `/invoices/{id}` | |
| GET | `/payment-requests/{id}` | Request, account, risk, gateway decision, approvals |
| POST | `/payment-requests/{id}/approvals` | `{"approved": true}` — approve or reject |
| GET | `/vendors/{id}/bank-change` | Current and proposed bank account |

## What is temporary

| Now | Later | Who |
|---|---|---|
| Sign-in by `X-User-Id` header (sample ids in `app/store.py`) | JWT | Karim |
| In-memory `Store` with sample data | PostgreSQL | Karim |
| `LocalGateway`: rules and an HMAC signature in-process | Calls to `services/gateway` | Anan |
| Risk scores in the sample data | `services/risk` | Ziad |

## Rules the tests hold

- Another company's records are 404, never 403.
- The creator of a payment request cannot approve it; accountants and viewers cannot approve.
- Above the dual-approval limit (`DUAL_APPROVAL_THRESHOLD_EGP`), two approvals; one rejection blocks.
- An approval signs the exact amount and IBAN; changing either breaks the signature.
- Approving needs a verified bank account (not one on hold).
- Gateway down or slow → block; nothing is recorded.

## Service rules
- Import shared types from `securefin_contracts` — never redefine them here.
- Need data owned by another service? Call its endpoint; do not write its tables.
- Document every new endpoint in this README.
