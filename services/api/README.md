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
| GET | `/payment-requests/{id}` | Request, account, risk, the gateway's latest approval answer, approvals |
| POST | `/payment-requests/{id}/approvals` | `{"approved": true, "comment": ""}` — sent to the gateway as `ApprovalRequest` |
| POST | `/payment-requests/{id}/execute` | Simulated payment, only if the gateway's execute-check allows |
| GET | `/vendors/{id}/bank-change` | Current and proposed bank account |
| GET | `/payments/{id}` | Internal, for the gateway: `PaymentRequestInfo`. Needs `X-Service-Token` |

## Calls to services/gateway

`GATEWAY_URL` (default `http://gateway:8000`), `GATEWAY_TIMEOUT_MS` (default 5000).

- Approve or reject → `POST /v1/approvals/{id}` with `approver_role` and `company_id` from the session.
  The gateway's 403/404/409/422 come back with its reasons; 503, timeouts or an unreadable answer → 503, nothing approved.
- Execute → `POST /v1/execute-check` first; pay only on `allowed: true`, then set `PAID_SIMULATED`.
- After approvals the status stays `PENDING_APPROVAL`: execute-check only allows a payment in that status.

## Database

With `DATABASE_URL` set the api uses PostgreSQL (`app/sql_store.py`); without it, the in-memory
sample data (`app/store.py`), as before. Both implement `DataStore`, and every api test runs on each.

```bash
export DATABASE_URL=postgresql+psycopg://securefin:change-me@localhost:5432/securefin
alembic upgrade head              # from services/api
python -m app.seed                # sample data, only into an empty database
python -m app.seed --refresh-dates  # sample requests back inside the gateway's 72 h window
```

Migration `0001` creates the api's tables plus `approvals` and `audit_log` (issue #15). Only the
gateway writes those two, and a trigger rejects UPDATE, DELETE and TRUNCATE on them for every user.
`approval_responses` is the api's copy of each answer the gateway gave, for the screens.

Run the api tests on PostgreSQL too (the database's tables are dropped):
`TEST_DATABASE_URL=postgresql+psycopg://... pytest`

## Deploy on Vercel

Vercel installs from `pyproject.toml` + `uv.lock` (entrypoint `app.main:app`, Python 3.12).
`.vercelignore` hides `requirements*.txt`, which stay for Docker and CI. After changing
dependencies, update both lists and run `uv lock` in this folder.

1. **Project:** Vercel → Add New → Project → import `USRAZz/DEPI-Final-Project`.
   Root Directory: `services/api`. Keep **"Include files outside the root directory in the Build Step"**
   on: the contracts at `../../contracts` are installed from there.
2. **Database:** Project → Storage → Create → Neon (Postgres) → connect it to the project.
   It sets `DATABASE_URL`; `postgres://` URLs are accepted (the psycopg driver is added).
3. **Environment variables** (Project → Settings → Environment Variables):

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | Neon's pooled URL (host with `-pooler`), set by step 2 |
   | `INTERNAL_SERVICE_TOKEN` | a long random string, the same one the gateway and risk service use |
   | `GATEWAY_URL` | the gateway's deployment URL, once it is deployed |
   | `DEV_LOGIN` | `1` only while testing with the sample users; leave unset otherwise |

   Without `DEV_LOGIN=1`, the `X-User-Id` sign-in is off on Vercel: anyone could claim any user.
4. **Schema and sample data**, from your machine against Neon's *direct* (non-pooler) URL:
   ```bash
   export DATABASE_URL="<Neon direct URL>"
   alembic upgrade head
   python -m app.seed
   ```
5. **Check:** `curl https://<project>.vercel.app/health` → `{"service":"api","status":"ok"}`.

On Vercel each request may run on a fresh instance, so nothing is kept in memory between
requests: all state is in Postgres. Approvals still need the gateway to store them in the
`approvals` table (today it keeps them in memory).

## What is temporary

| Now | Later | Who |
|---|---|---|
| Sign-in by `X-User-Id` header (sample ids in `app/store.py`) | JWT | Karim |
| Risk scores in the sample data | `services/risk` | Ziad |
| Gateway keeps approvals in memory (`InMemoryApprovalStore`) | Gateway writes the `approvals` table | Anan |

## Rules the tests hold

Tests run against `tests/fakes.py`, an in-process stand-in that follows the gateway's rules.

- Another company's records are 404, never 403.
- Role and company sent to the gateway come from the session; a body that tries to set them is rejected (422).
- Accountants and viewers cannot approve; approvers and viewers cannot execute. Neither reaches the gateway.
- The gateway's refusal reasons (maker-checker, already decided) reach the caller unchanged.
- A payment runs only when execute-check allows it, and only once.
- Approving or paying needs a verified bank account (not one on hold).
- Gateway down or slow → 503; nothing approved, nothing paid.

## Service rules
- Import shared types from `securefin_contracts` — never redefine them here.
- Need data owned by another service? Call its endpoint; do not write its tables.
- Document every new endpoint in this README.
