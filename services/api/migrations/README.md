Alembic migrations live ONLY here (owner: M4 Ziad, the database owner). CI fails if there is more than one head.
Other owners: open an issue labelled `schema` or add a migration after rebasing on latest `dev`.

## Run

```bash
docker compose exec api alembic upgrade head      # inside the container (DATABASE_URL from .env)
cd services/api && alembic upgrade head           # locally, with DATABASE_URL set
```

## Row-level security (0001)

Every tenant table is filtered by `app.company_id`. Without it, queries return zero rows.
Superusers and table owners skip RLS, so services must switch to the `securefin_app` role in each transaction:

```sql
BEGIN;
SET LOCAL ROLE securefin_app;
SELECT set_config('app.company_id', '42', true);  -- company id from the user's session, never from the request body
-- queries
COMMIT;
```

Write ownership (issue #15): `approvals` and `audit_log` belong to the gateway. Role `securefin_gateway` may only
SELECT and INSERT them (append-only); `securefin_app` (the api) has no access to them and reads through gateway
endpoints. `approvals.expires_at` defaults to 72 hours after signing. `audit_log` columns follow the `AuditEntry` contract
plus `company_id`; the chain starts with `prev_hash = '0' * 64`.

## Decisions in 0001

| Question | Decision |
|---|---|
| ids | Integers (BIGINT identity), as in the shared contracts |
| RLS | On from the first migration |
| Duplicates | Same file blocked: UNIQUE (company_id, source_hash). Same vendor + invoice number: index only, flagged for review |
| Files | Docker volume; the row stores key, sha256, MIME, size |
| Statuses | Shared `InvoiceStatus` values |

Test: `tests/test_migrations.py` (needs `TEST_DATABASE_URL`, an empty PostgreSQL; CI job `migrations-postgres`).
