"""Migration 0001 and row-level security against a real PostgreSQL. Skipped unless TEST_DATABASE_URL is set
(CI sets it with a postgres service). Everything in its public schema is dropped first.

    docker run -d --rm --name sf-pg -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:16
    TEST_DATABASE_URL=postgresql+psycopg://postgres:test@localhost:55432/postgres pytest tests/test_migrations.py
"""
import os
from pathlib import Path

import pytest

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")

API = Path(__file__).resolve().parents[1]
SEED = """
INSERT INTO companies (name, default_language, created_at) VALUES ('A', 'ar', now()), ('B', 'en', now());
INSERT INTO users (company_id, email, full_name, role, language, is_active, created_at) VALUES
    (1, 'maker@a.eg', 'Maker', 'accountant', 'ar', true, now()),
    (1, 'boss@a.eg', 'Boss', 'approver', 'ar', true, now()),
    (2, 'x@b.eg', 'X', 'admin', 'en', true, now());
INSERT INTO vendors (company_id, name, created_at) VALUES (1, 'Nile', now()), (2, 'Delta', now());
INSERT INTO bank_accounts (company_id, vendor_id, bank_name, iban, status, times_paid, created_at)
    VALUES (1, 1, 'NBE', 'EG380019000500000000263180002', 'verified', 0, now());
INSERT INTO invoices (company_id, vendor_id, source, status, file_key, created_at, extraction_issues)
    VALUES (1, 1, 'upload', 'VALIDATED', 'k1', now(), '[]');
INSERT INTO payment_requests (company_id, invoice_id, vendor_id, bank_account_id, creator_id, amount, currency,
                              status, note, created_at)
    VALUES (1, 1, 1, 1, 1, 1500, 'EGP', 'PENDING_APPROVAL', '', now());
"""


def _cfg():
    from alembic.config import Config
    cfg = Config(str(API / "alembic.ini"))
    cfg.set_main_option("script_location", str(API / "migrations"))
    return cfg


@pytest.fixture(scope="module")
def engine():
    from alembic import command
    from sqlalchemy import create_engine, text

    os.environ["DATABASE_URL"] = URL
    eng = create_engine(URL)
    with eng.begin() as c:  # start from an empty schema, whatever an earlier test left behind
        c.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT USAGE ON SCHEMA public TO PUBLIC")
    command.upgrade(_cfg(), "head")
    with eng.begin() as c:  # superuser: seeds two tenants (RLS does not apply to superusers)
        c.execute(text(SEED))
    yield eng
    eng.dispose()
    command.downgrade(_cfg(), "base")


def _as(conn, company_id=None, role="securefin_app"):
    from sqlalchemy import text
    conn.execute(text(f"SET LOCAL ROLE {role}"))
    if company_id is not None:
        conn.execute(text("SELECT set_config('app.company_id', :c, true)"), {"c": str(company_id)})


APPROVAL = ("INSERT INTO approvals (company_id, payment_request_id, approver_id, approve, hmac_signature, "
            "signed_at, expires_at) VALUES (:c, 1, 2, true, 'sig', now(), now() + interval '72 hours')")
AUDIT = ("INSERT INTO audit_log (timestamp, company_id, action, parameters, source_service, prev_hash, entry_hash) "
         "VALUES (now(), :c, 'authorize', '{}', 'gateway', :p, :e)")


def test_single_head_is_0001():
    from alembic.script import ScriptDirectory
    assert ScriptDirectory.from_config(_cfg()).get_heads() == ["0001"]


def test_database_matches_the_orm(engine):
    """app/db.py and the migrated database describe the same tables (a model change needs a migration)."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.db import Base
    with engine.connect() as c:
        assert compare_metadata(MigrationContext.configure(c), Base.metadata) == []


def test_rows_cannot_point_at_another_companys_rows(engine):
    from sqlalchemy import exc, text
    with pytest.raises(exc.IntegrityError, match="same_company"), engine.begin() as c:  # superuser: only the FK stops it
        c.execute(text("INSERT INTO invoices (company_id, vendor_id, source, status, file_key, created_at, "
                       "extraction_issues) VALUES (1, 2, 'upload', 'VALIDATED', 'k2', now(), '[]')"))


def test_status_and_role_only_take_contract_values(engine):
    from sqlalchemy import exc, text
    for stmt in ("UPDATE payment_requests SET status = 'PAID'", "UPDATE users SET role = 'root'"):
        with pytest.raises(exc.IntegrityError, match="ck_"), engine.begin() as c:
            c.execute(text(stmt))


def test_no_company_set_returns_zero_rows(engine):
    from sqlalchemy import text
    with engine.begin() as c:
        _as(c)
        assert c.execute(text("SELECT count(*) FROM vendors")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM companies")).scalar() == 0


def test_each_company_sees_only_its_own_rows(engine):
    from sqlalchemy import text
    with engine.begin() as c:
        _as(c, 1)
        assert c.execute(text("SELECT name FROM vendors")).scalars().all() == ["Nile"]
        assert c.execute(text("SELECT count(*) FROM users")).scalar() == 2
        assert c.execute(text("SELECT count(*) FROM payment_requests")).scalar() == 1
    with engine.begin() as c:
        _as(c, 2)
        assert c.execute(text("SELECT count(*) FROM payment_requests")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM payment_risk")).scalar() == 0


def test_cannot_write_into_another_company(engine):
    from sqlalchemy import exc, text
    with pytest.raises(exc.ProgrammingError, match="row-level security"), engine.begin() as c:
        _as(c, 1)
        c.execute(text("INSERT INTO vendors (company_id, name, created_at) VALUES (2, 'Evil', now())"))


def test_api_role_can_write_its_own_tables(engine):
    from sqlalchemy import text
    with engine.begin() as c:
        _as(c, 1)
        c.execute(text("INSERT INTO vendors (company_id, name, created_at) VALUES (1, 'Giza', now())"))
        c.execute(text("UPDATE payment_requests SET note = 'checked'"))


def test_api_cannot_forge_an_approval_or_read_the_audit_log(engine):
    from sqlalchemy import exc, text
    with pytest.raises(exc.ProgrammingError, match="permission denied"), engine.begin() as c:
        _as(c, 1)
        c.execute(text(APPROVAL), {"c": 1})
    with pytest.raises(exc.ProgrammingError, match="permission denied"), engine.begin() as c:
        _as(c, 1)
        c.execute(text("SELECT count(*) FROM audit_log"))


def test_gateway_approvals_are_append_only_and_one_per_approver(engine):
    from sqlalchemy import exc, text
    with engine.begin() as c:
        _as(c, 1, role="securefin_gateway")
        c.execute(text(APPROVAL), {"c": 1})
    with pytest.raises(exc.IntegrityError), engine.begin() as c:  # the same person cannot approve twice
        _as(c, 1, role="securefin_gateway")
        c.execute(text(APPROVAL), {"c": 1})
    with pytest.raises(exc.ProgrammingError, match="row-level security"), engine.begin() as c:
        _as(c, 1, role="securefin_gateway")
        c.execute(text(APPROVAL), {"c": 2})
    for stmt in ("UPDATE approvals SET approve = false", "DELETE FROM approvals"):
        with pytest.raises(exc.ProgrammingError, match="permission denied"), engine.begin() as c:
            _as(c, 1, role="securefin_gateway")
            c.execute(text(stmt))
    with engine.begin() as c:
        _as(c, 2, role="securefin_gateway")
        assert c.execute(text("SELECT count(*) FROM approvals")).scalar() == 0


def test_gateway_audit_log_is_append_only_and_per_company(engine):
    from sqlalchemy import exc, text
    with engine.begin() as c:
        _as(c, 1, role="securefin_gateway")
        c.execute(text(AUDIT), {"c": 1, "p": "0" * 64, "e": "1" * 64})
    with pytest.raises(exc.ProgrammingError, match="row-level security"), engine.begin() as c:
        _as(c, 1, role="securefin_gateway")
        c.execute(text(AUDIT), {"c": 2, "p": "1" * 64, "e": "2" * 64})
    with pytest.raises(exc.ProgrammingError, match="permission denied"), engine.begin() as c:
        _as(c, 1, role="securefin_gateway")
        c.execute(text("UPDATE audit_log SET decision = 'ALLOW'"))


def test_even_the_owner_cannot_edit_history(engine):
    from sqlalchemy import exc, text
    for stmt in ("UPDATE audit_log SET decision = 'BLOCK'", "DELETE FROM approvals", "TRUNCATE audit_log"):
        with pytest.raises(exc.DatabaseError, match="append-only"), engine.begin() as c:
            c.execute(text(stmt))


def test_money_columns_are_numeric(engine):
    from sqlalchemy import text
    with engine.begin() as c:
        types = dict(c.execute(text(
            "SELECT table_name || '.' || column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = 'amount'")).all())
    assert types and set(types.values()) == {"numeric"}
