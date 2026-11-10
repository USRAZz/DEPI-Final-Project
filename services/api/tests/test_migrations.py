"""Migration + row-level security against a real PostgreSQL. Skipped unless TEST_DATABASE_URL is set
(CI sets it with a postgres service). The database must be empty: the test upgrades and downgrades it.

    docker run -d --rm --name sf-pg -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:16
    TEST_DATABASE_URL=postgresql+psycopg://postgres:test@localhost:55432/postgres pytest tests/test_migrations.py
"""
import os
from pathlib import Path

import pytest

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")

HASH = "a" * 64


@pytest.fixture(scope="module")
def engine():
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    os.environ["DATABASE_URL"] = URL
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    command.upgrade(cfg, "head")
    eng = create_engine(URL)
    with eng.begin() as c:  # superuser: seeds two tenants (RLS does not apply to superusers)
        c.execute(text("INSERT INTO companies (name) VALUES ('A'), ('B')"))
        c.execute(text("INSERT INTO users (company_id, email, role) VALUES "
                       "(1, 'maker@a.eg', 'accountant'), (1, 'boss@a.eg', 'approver'), (2, 'x@b.eg', 'admin')"))
        c.execute(text("INSERT INTO vendors (company_id, name) VALUES (1, 'Nile'), (2, 'Delta')"))
    yield eng
    eng.dispose()
    command.downgrade(cfg, "base")


def _as_app(conn, company_id=None, role="securefin_app"):
    from sqlalchemy import text
    conn.execute(text(f"SET LOCAL ROLE {role}"))
    if company_id is not None:
        conn.execute(text("SELECT set_config('app.company_id', :c, true)"), {"c": str(company_id)})


def test_no_company_set_returns_zero_rows(engine):
    from sqlalchemy import text
    with engine.begin() as c:
        _as_app(c)
        assert c.execute(text("SELECT count(*) FROM vendors")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM companies")).scalar() == 0


def test_each_company_sees_only_its_own_rows(engine):
    from sqlalchemy import text
    with engine.begin() as c:
        _as_app(c, 1)
        assert c.execute(text("SELECT name FROM vendors")).scalars().all() == ["Nile"]
        assert c.execute(text("SELECT count(*) FROM users")).scalar() == 2


def test_cannot_write_into_another_company(engine):
    from sqlalchemy import exc, text
    with pytest.raises(exc.ProgrammingError, match="row-level security"), engine.begin() as c:
        _as_app(c, 1)
        c.execute(text("INSERT INTO vendors (company_id, name) VALUES (2, 'Evil')"))


def test_invoice_cannot_point_at_another_companys_vendor(engine):
    from sqlalchemy import exc, text
    with pytest.raises(exc.IntegrityError), engine.begin() as c:  # superuser: only the FK can stop it
        c.execute(text("INSERT INTO invoices (company_id, vendor_id, source_key, source_hash, source_mime, "
                       "source_size) VALUES (1, 2, 'k', :h, 'application/pdf', 10)"), {"h": HASH})


def test_same_file_twice_is_rejected_but_same_number_is_allowed(engine):
    from sqlalchemy import exc, text
    insert = text("INSERT INTO invoices (company_id, vendor_id, invoice_number, source_key, source_hash, "
                  "source_mime, source_size) VALUES (1, 1, 'A-1', :k, :h, 'application/pdf', 10)")
    with engine.begin() as c:
        _as_app(c, 1)
        c.execute(insert, {"k": "f1", "h": "b" * 64})
        c.execute(insert, {"k": "f2", "h": "c" * 64})  # same vendor + number: kept, flagged later
    with pytest.raises(exc.IntegrityError), engine.begin() as c:
        _as_app(c, 1)
        c.execute(insert, {"k": "f3", "h": "b" * 64})


APPROVAL = ("INSERT INTO approvals (company_id, payment_request_id, approver_id, approve, hmac_signature) "
            "VALUES (1, :p, 2, true, 'sig')")


@pytest.fixture(scope="module")
def payment_request(engine):
    from sqlalchemy import text
    with engine.begin() as c:
        _as_app(c, 1)
        inv = c.execute(text("INSERT INTO invoices (company_id, vendor_id, source_key, source_hash, source_mime, "
                             "source_size) VALUES (1, 1, 'pr', :h, 'application/pdf', 10) RETURNING id"),
                        {"h": "d" * 64}).scalar()
        return c.execute(text("INSERT INTO payment_requests (company_id, invoice_id, vendor_id, created_by, amount, "
                              "request_hash) VALUES (1, :i, 1, 1, 1500, :h) RETURNING id"),
                         {"i": inv, "h": HASH}).scalar()


def test_api_cannot_forge_an_approval_or_read_the_audit_log(engine, payment_request):
    from sqlalchemy import exc, text
    with pytest.raises(exc.ProgrammingError, match="permission denied"), engine.begin() as c:
        _as_app(c, 1)
        c.execute(text(APPROVAL), {"p": payment_request})
    with pytest.raises(exc.ProgrammingError, match="permission denied"), engine.begin() as c:
        _as_app(c, 1)
        c.execute(text("SELECT count(*) FROM audit_log"))


def test_gateway_approvals_are_append_only_and_expire_in_72h(engine, payment_request):
    from sqlalchemy import exc, text
    with engine.begin() as c:
        _as_app(c, 1, role="securefin_gateway")
        c.execute(text(APPROVAL), {"p": payment_request})
        hours = c.execute(text("SELECT extract(epoch FROM expires_at - signed_at) / 3600 FROM approvals")).scalar()
    assert round(hours) == 72
    with pytest.raises(exc.IntegrityError), engine.begin() as c:  # the same person cannot approve twice
        _as_app(c, 1, role="securefin_gateway")
        c.execute(text(APPROVAL), {"p": payment_request})
    for stmt in ("UPDATE approvals SET approve = false", "DELETE FROM approvals"):
        with pytest.raises(exc.ProgrammingError, match="permission denied"), engine.begin() as c:
            _as_app(c, 1, role="securefin_gateway")
            c.execute(text(stmt))


def test_gateway_audit_log_is_append_only_and_per_company(engine):
    from sqlalchemy import exc, text
    row = ("INSERT INTO audit_log (company_id, action, source_service, prev_hash, entry_hash) "
           "VALUES (:c, 'authorize', 'gateway', :p, :e)")
    with engine.begin() as c:
        _as_app(c, 1, role="securefin_gateway")
        c.execute(text(row), {"c": 1, "p": "0" * 64, "e": "1" * 64})
    with pytest.raises(exc.ProgrammingError, match="row-level security"), engine.begin() as c:
        _as_app(c, 1, role="securefin_gateway")
        c.execute(text(row), {"c": 2, "p": "1" * 64, "e": "2" * 64})
    with pytest.raises(exc.ProgrammingError, match="permission denied"), engine.begin() as c:
        _as_app(c, 1, role="securefin_gateway")
        c.execute(text("UPDATE audit_log SET decision = 'ALLOW'"))


def test_money_columns_are_numeric(engine):
    from sqlalchemy import text
    with engine.begin() as c:
        types = dict(c.execute(text(
            "SELECT table_name || '.' || column_name, data_type FROM information_schema.columns "
            "WHERE column_name IN ('amount', 'total', 'subtotal', 'unit_price', 'quantity')")).all())
    assert types and set(types.values()) == {"numeric"}
