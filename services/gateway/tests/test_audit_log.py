"""Issue #16: every approval / execute-check outcome writes a hash-chained audit entry."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import app.main as main
import pytest
from app.audit_log import InMemoryAuditLog
from app.stores import InMemoryApprovalStore
from fastapi.testclient import TestClient
from securefin_contracts import AuditEvent, InvoiceStatus, PaymentRequestInfo

client = TestClient(main.app)


class FakePayments:
    def get(self, payment_request_id):
        return PaymentRequestInfo(id=1, company_id=1, creator_id=7, invoice_id=2, vendor_id=3, amount=Decimal("500"),
                                  currency="EGP", status=InvoiceStatus.PENDING_APPROVAL,
                                  created_at=datetime.now(UTC) - timedelta(hours=1))


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setenv("APPROVAL_HMAC_KEY", "k" * 40)
    monkeypatch.setattr(main, "APPROVAL_STORE", InMemoryApprovalStore())
    monkeypatch.setattr(main, "PAYMENTS_CLIENT", FakePayments())
    monkeypatch.setattr(main, "AUDIT_LOG", InMemoryAuditLog())


def _approve(approver_id, company_id=1):
    return client.post("/v1/approvals/1", json={"payment_request_id": 1, "approver_id": approver_id, "approve": True,
                                                "approver_role": "approver", "company_id": company_id})


def test_every_outcome_is_audited_and_the_chain_holds():
    assert _approve(7).status_code == 403                                   # maker approves own request
    assert _approve(10).json()["status"] == "APPROVED"
    assert _approve(10).status_code == 403                                  # second vote
    client.post("/v1/execute-check", json={"payment_request_id": 1, "requested_by": 7, "company_id": 1})
    log = main.AUDIT_LOG.entries(1)
    assert [(e.action, e.decision) for e in log] == [
        ("approval", "BLOCK"), ("approval", "APPROVED"), ("approval", "BLOCK"), ("execute_check", "ALLOW")]
    assert "maker-checker" in log[0].result and log[0].user_id == 7
    assert all(e.source_service == "gateway" for e in log)
    assert main.AUDIT_LOG.verify(1) is None


def test_missing_signing_key_is_audited(monkeypatch):
    monkeypatch.delenv("APPROVAL_HMAC_KEY")
    assert _approve(10).status_code == 503
    assert main.AUDIT_LOG.entries(1)[0].result.startswith("503")


def test_editing_an_entry_breaks_the_chain():
    log = InMemoryAuditLog()
    for action in ("a", "b", "c"):
        log.append(AuditEvent(user_id=1, company_id=1, action=action, source_service="gateway"))
    log._entries[1] = log._entries[1].model_copy(update={"decision": "ALLOW"})  # tampered after the fact
    assert log.verify(1) == 1


def test_each_company_has_its_own_chain():
    log = InMemoryAuditLog()
    a = log.append(AuditEvent(user_id=1, company_id=1, action="x", source_service="gateway"))
    b = log.append(AuditEvent(user_id=2, company_id=2, action="x", source_service="gateway"))
    assert a.prev_hash == b.prev_hash == "0" * 64
