"""Approvals and audit_log in PostgreSQL through role securefin_gateway (migration 0001, issues #15 and #16).
Skipped unless TEST_DATABASE_URL points at an EMPTY database (the test upgrades and downgrades it)."""
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")
API = Path(__file__).resolve().parents[2] / "api"


@pytest.fixture(scope="module")
def engine():
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    os.environ["DATABASE_URL"] = URL
    cfg = Config(str(API / "alembic.ini"))
    cfg.set_main_option("script_location", str(API / "migrations"))
    command.upgrade(cfg, "head")
    eng = create_engine(URL)
    with eng.begin() as c:  # superuser seeds what the api would own
        c.execute(text("INSERT INTO companies (name) VALUES ('A'), ('B')"))
        c.execute(text("INSERT INTO users (company_id, email, role) VALUES (1, 'm@a.eg', 'accountant'), "
                       "(1, 'b@a.eg', 'approver'), (2, 'x@b.eg', 'approver')"))
        c.execute(text("INSERT INTO vendors (company_id, name) VALUES (1, 'Nile')"))
        c.execute(text("INSERT INTO invoices (company_id, vendor_id, source_key, source_hash, source_mime, source_size) "
                       "VALUES (1, 1, 'k', repeat('a', 64), 'application/pdf', 10)"))
        c.execute(text("INSERT INTO payment_requests (company_id, invoice_id, vendor_id, created_by, amount, request_hash) "
                       "VALUES (1, 1, 1, 1, 1500, repeat('b', 64))"))
    yield eng
    eng.dispose()
    command.downgrade(cfg, "base")


def _record(approver_id=2):
    from securefin_contracts import ApprovalRecord
    return ApprovalRecord(payment_request_id=1, approver_id=approver_id, approve=True, hmac_signature="s" * 64,
                          signed_at=datetime.now(UTC))


def test_store_round_trip_keeps_the_signed_timestamp(engine):
    from app.stores import PostgresApprovalStore
    store = PostgresApprovalStore(engine, expiry_hours=72)
    rec = _record()
    store.add(rec, company_id=1)
    assert store.list(1, company_id=1) == [rec]  # same signed_at -> the HMAC still verifies after reading back
    assert store.list(1, company_id=2) == []     # another company sees nothing


def test_second_vote_is_a_duplicate(engine):
    from app.stores import DuplicateApprovalError, PostgresApprovalStore
    with pytest.raises(DuplicateApprovalError):
        PostgresApprovalStore(engine, expiry_hours=72).add(_record(), company_id=1)


def test_store_refuses_without_company(engine):
    from app.stores import PostgresApprovalStore
    with pytest.raises(ValueError):
        PostgresApprovalStore(engine, expiry_hours=72).list(1)


def test_audit_chain_survives_the_database_and_detects_edits(engine):
    from app.audit_log import PostgresAuditLog
    from securefin_contracts import AuditEvent
    from sqlalchemy import text
    log = PostgresAuditLog(engine)
    for action in ("approval", "approval", "execute_check"):
        log.append(AuditEvent(user_id=2, company_id=1, action=action, parameters={"payment_request_id": 1, "x": 1.5},
                              decision="ALLOW", source_service="gateway"))
    log.append(AuditEvent(user_id=3, company_id=2, action="approval", source_service="gateway"))
    assert log.verify(1) is None and log.verify(2) is None
    assert log.entries(2)[0].prev_hash == "0" * 64
    with engine.begin() as c:  # a superuser edits history behind the gateway's back
        c.execute(text("UPDATE audit_log SET decision = 'BLOCK' WHERE company_id = 1 AND id = "
                       "(SELECT min(id) FROM audit_log WHERE company_id = 1) + 1"))
    assert log.verify(1) == 1
