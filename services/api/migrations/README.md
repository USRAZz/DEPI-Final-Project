Alembic migrations live ONLY here (owner: M4 Ziad, the database owner). CI fails if there is more than one head.
Other owners: open an issue labelled `schema` or add a migration after rebasing on latest `dev`.

## Run

```bash
docker compose exec api alembic upgrade head      # inside the container (DATABASE_URL from .env)
cd services/api && alembic upgrade head           # locally, with DATABASE_URL set
```

New migration from a change in `app/db.py`: `cd services/api && alembic revision --autogenerate -m "..."`, then read it.

## 0001: the whole schema

`0001` creates every table from `app/db.py` (autogenerate) and the security layer in the same migration:

- Every tenant row carries `company_id`; references are `(company_id, x_id)`, so a row cannot point at another
  company's vendor, user, invoice or account.
- Status, role, language and source columns only accept the shared contract values (CHECK constraints).
- `approvals` and `audit_log` are append-only for everyone (trigger: no UPDATE, DELETE or TRUNCATE).
- Roles `securefin_app` (api) and `securefin_gateway`, and row-level security by `app.company_id`.

`tests/test_migrations.py` fails when `app/db.py` and the migrated database differ.

## Row-level security

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
  the owner login is not filtered. The api's `SqlStore` runs every read for one company as `securefin_app`; lookups
  that come before the company is known (the signed-in user, service-to-service reads by id) use the owner login.
- `audit_log` columns follow the `AuditEntry` contract plus `company_id`; each company's chain starts with
  `prev_hash = '0' * 64`.

Tests: `tests/test_migrations.py` and `services/gateway/tests/test_db_store_audit.py` (need `TEST_DATABASE_URL`, an empty
PostgreSQL; CI job `migrations-postgres`).
