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


def _as_app(conn, company_id=None):
    from sqlalchemy import text
    conn.execute(text("SET LOCAL ROLE securefin_app"))
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


def test_approvals_are_append_only_for_the_app(engine):
    from sqlalchemy import exc, text
    with engine.begin() as c:
        _as_app(c, 1)
        inv = c.execute(text("SELECT id FROM invoices LIMIT 1")).scalar()
        pr = c.execute(text("INSERT INTO payment_requests (company_id, invoice_id, vendor_id, created_by, amount, "
                            "request_hash) VALUES (1, :i, 1, 1, 1500, :h) RETURNING id"),
                       {"i": inv, "h": HASH}).scalar()
        c.execute(text("INSERT INTO approvals (company_id, payment_request_id, approver_id, approve, hmac_signature) "
                       "VALUES (1, :p, 2, true, 'sig')"), {"p": pr})
    with pytest.raises(exc.ProgrammingError, match="permission denied"), engine.begin() as c:
        _as_app(c, 1)
        c.execute(text("UPDATE approvals SET approve = false"))


def test_money_columns_are_numeric(engine):
    from sqlalchemy import text
    with engine.begin() as c:
        types = dict(c.execute(text(
            "SELECT table_name || '.' || column_name, data_type FROM information_schema.columns "
            "WHERE column_name IN ('amount', 'total', 'subtotal', 'unit_price', 'quantity')")).all())
    assert types and set(types.values()) == {"numeric"}
