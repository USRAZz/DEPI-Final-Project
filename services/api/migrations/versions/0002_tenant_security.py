"""tenant security: database roles, row-level security, gateway-only approvals and audit_log

0001 creates the tables the api's ORM uses (app/db.py). This adds the security layer on top (issues #15, #16):

- approvals gets company_id, so every gateway table can be filtered by tenant.
- Role securefin_gateway: the only role that may touch approvals and audit_log, and only SELECT + INSERT.
  Both tables FORCE row-level security, so even the table owner sees one company at a time.
- Role securefin_app: the api's role. Full access to the api tables, none to approvals/audit_log.
  The api tables have row-level security ENABLED (not forced): connections that switch to securefin_app see one
  company; the migration/owner login keeps working as before.

How a service connects (superusers skip RLS; owners skip it unless FORCE is on):
    BEGIN;
    SET LOCAL ROLE securefin_gateway;   -- or securefin_app
    SELECT set_config('app.company_id', '<company id from the session>', true);
    ... queries ...
    COMMIT;
No app.company_id -> zero rows.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-13
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APP_ROLE = "securefin_app"          # api
GATEWAY_ROLE = "securefin_gateway"  # gateway: the only writer of approvals and audit_log
TENANT = "NULLIF(current_setting('app.company_id', true), '')::integer"

API_TABLES = ("users", "vendors", "bank_accounts", "invoices", "payment_requests", "approval_responses")
GATEWAY_TABLES = ("approvals", "audit_log")
API_SEQUENCES = ("companies_id_seq", "users_id_seq", "vendors_id_seq", "bank_accounts_id_seq", "invoices_id_seq",
                 "payment_requests_id_seq", "approval_responses_id_seq")
GATEWAY_SEQUENCES = ("approvals_id_seq", "audit_log_id_seq")


def _policy(table: str, using: str) -> str:
    return (f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;"
            f"CREATE POLICY tenant_isolation ON {table} USING ({using}) WITH CHECK ({using});")


def upgrade() -> None:
    # approvals.company_id, filled from the payment request (the append-only trigger is paused for the backfill).
    op.execute("ALTER TABLE approvals ADD COLUMN company_id INTEGER REFERENCES companies(id)")
    op.execute("ALTER TABLE approvals DISABLE TRIGGER approvals_append_only")
    op.execute("UPDATE approvals a SET company_id = p.company_id FROM payment_requests p "
               "WHERE p.id = a.payment_request_id")
    op.execute("ALTER TABLE approvals ENABLE TRIGGER approvals_append_only")
    op.execute("ALTER TABLE approvals ALTER COLUMN company_id SET NOT NULL")
    op.execute("CREATE INDEX ix_approvals_company_id ON approvals (company_id)")

    for role in (APP_ROLE, GATEWAY_ROLE):
        op.execute(f"""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                    CREATE ROLE {role} NOLOGIN;
                END IF;
                -- the login that runs the services must be allowed to SET ROLE to it (Neon, managed Postgres)
                EXECUTE format('GRANT {role} TO %I', current_user);
            EXCEPTION WHEN insufficient_privilege OR invalid_grant_operation THEN
                RAISE NOTICE 'could not grant {role} to %: grant it by hand', current_user;
            END $$;
        """)

    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}, {GATEWAY_ROLE}")

    # api tables: RLS enabled, api role gets read/write
    op.execute(_policy("companies", f"id = {TENANT}"))
    for t in API_TABLES:
        op.execute(_policy(t, f"company_id = {TENANT}"))
    op.execute(_policy("payment_risk", "EXISTS (SELECT 1 FROM payment_requests p "
                                       f"WHERE p.id = payment_request_id AND p.company_id = {TENANT})"))
    op.execute(f"GRANT SELECT ON companies TO {APP_ROLE}")
    for t in API_TABLES + ("payment_risk",):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO {APP_ROLE}")
    for s in API_SEQUENCES:
        op.execute(f"GRANT USAGE ON SEQUENCE {s} TO {APP_ROLE}")

    # gateway tables: RLS forced, append-only, gateway role only
    for t in GATEWAY_TABLES:
        op.execute(_policy(t, f"company_id = {TENANT}") + f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY;")
        op.execute(f"REVOKE ALL ON {t} FROM PUBLIC, {APP_ROLE}")
        op.execute(f"GRANT SELECT, INSERT ON {t} TO {GATEWAY_ROLE}")
    for s in GATEWAY_SEQUENCES:
        op.execute(f"GRANT USAGE ON SEQUENCE {s} TO {GATEWAY_ROLE}")


def downgrade() -> None:
    for t in ("companies", "payment_risk") + API_TABLES + GATEWAY_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t};"
                   f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY; ALTER TABLE {t} DISABLE ROW LEVEL SECURITY;")
    for role in (APP_ROLE, GATEWAY_ROLE):
        op.execute(f"""
            DO $$ BEGIN
                IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                    EXECUTE 'DROP OWNED BY {role}';
                    DROP ROLE {role};
                END IF;
            END $$;
        """)
    op.execute("DROP INDEX IF EXISTS ix_approvals_company_id")
    op.execute("ALTER TABLE approvals DROP COLUMN company_id")
