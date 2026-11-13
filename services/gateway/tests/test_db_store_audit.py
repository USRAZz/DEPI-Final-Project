"""Approvals and audit_log in PostgreSQL through role securefin_gateway (migration 0001, issues #15 and #16).
Skipped unless TEST_DATABASE_URL is set; everything in that database's public schema is dropped first."""
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
    eng = create_engine(URL)
    with eng.begin() as c:  # start from an empty schema, whatever an earlier test left behind
        c.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT USAGE ON SCHEMA public TO PUBLIC")
    command.upgrade(cfg, "head")
    with eng.begin() as c:  # superuser seeds what the api would own
        c.execute(text("""
            INSERT INTO companies (name, default_language, created_at) VALUES ('A', 'ar', now()), ('B', 'en', now());
            INSERT INTO users (company_id, email, full_name, role, language, is_active, created_at) VALUES
                (1, 'm@a.eg', 'M', 'accountant', 'ar', true, now()), (1, 'b@a.eg', 'B', 'approver', 'ar', true, now()),
                (2, 'x@b.eg', 'X', 'approver', 'en', true, now());
            INSERT INTO vendors (company_id, name, created_at) VALUES (1, 'Nile', now());
            INSERT INTO bank_accounts (company_id, vendor_id, bank_name, iban, status, times_paid, created_at)
                VALUES (1, 1, 'NBE', 'EG380019000500000000263180002', 'verified', 0, now());
            INSERT INTO invoices (company_id, vendor_id, source, status, file_key, file_sha256, created_at,
                                      extraction_issues)
                VALUES (1, 1, 'upload', 'VALIDATED', 'k', repeat('a', 64), now(), '[]');
            INSERT INTO payment_requests (company_id, invoice_id, vendor_id, bank_account_id, creator_id, amount,
                                          currency, status, note, created_at)
                VALUES (1, 1, 1, 1, 1, 1500, 'EGP', 'PENDING_APPROVAL', '', now());
        """))
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
    with engine.begin() as c:  # a superuser switches off the append-only trigger and edits history
        c.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only"))
        c.execute(text("UPDATE audit_log SET decision = 'BLOCK' WHERE company_id = 1 AND id = "
                       "(SELECT min(id) FROM audit_log WHERE company_id = 1) + 1"))
        c.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only"))
    assert log.verify(1) == 1
