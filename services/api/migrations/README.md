Alembic migrations live ONLY here (owner: M4 Ziad, the database owner). CI fails if there is more than one head.
Other owners: open an issue labelled `schema` or add a migration after rebasing on latest `dev`.

## Run

```bash
docker compose exec api alembic upgrade head      # inside the container (DATABASE_URL from .env)
cd services/api && alembic upgrade head           # locally, with DATABASE_URL set
```

New migration from a change in `app/db.py`: `cd services/api && alembic revision --autogenerate -m "..."`, then read it.

## What each migration does

| Revision | Content |
|---|---|
| `0001` | The api tables from `app/db.py` (companies, users, vendors, bank_accounts, invoices, payment_requests, approval_responses, payment_risk) plus `approvals` and `audit_log`. A trigger makes `approvals` and `audit_log` append-only for everyone (no UPDATE, DELETE or TRUNCATE). |
| `0002` | Security layer: `approvals.company_id`, roles `securefin_app` and `securefin_gateway`, row-level security by `app.company_id`. |

## Row-level security (0002)

Each tenant table is filtered by the transaction setting `app.company_id`. Without it, queries return zero rows.
A service switches role in each transaction:

```sql
BEGIN;
SET LOCAL ROLE securefin_gateway;                 -- the api uses securefin_app
SELECT set_config('app.company_id', '42', true);  -- company id from the user's session, never from the request body
-- queries
COMMIT;
```

- `approvals` and `audit_log` belong to the gateway (issue #15). RLS is **forced** on them, `securefin_gateway` may only
  SELECT and INSERT, and `securefin_app` (the api) has no access at all; the api keeps its own copy of each answer in
  `approval_responses`. The gateway sets `expires_at` (72 hours after signing).
- The api tables have RLS **enabled, not forced**: a connection that switches to `securefin_app` sees one company;
  the owner login (migrations, the current api) is not filtered. Moving the api onto `securefin_app` is the next step.
- `audit_log` columns follow the `AuditEntry` contract plus `company_id`; each company's chain starts with
  `prev_hash = '0' * 64`.

Tests: `tests/test_migrations.py` and `services/gateway/tests/test_db_store_audit.py` (need `TEST_DATABASE_URL`, an empty
PostgreSQL; CI job `migrations-postgres`).
