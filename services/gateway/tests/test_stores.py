from datetime import UTC, datetime

import pytest
from app.stores import DuplicateApprovalError, InMemoryApprovalStore
from securefin_contracts import ApprovalRecord


def rec(pid=1, approver=10):
    return ApprovalRecord(payment_request_id=pid, approver_id=approver, approve=True, hmac_signature="x" * 64,
                          signed_at=datetime.now(UTC))


def test_add_and_list_by_payment():
    s = InMemoryApprovalStore()
    s.add(rec(1, 10))
    s.add(rec(1, 11))
    s.add(rec(2, 10))
    assert {r.approver_id for r in s.list(1)} == {10, 11}
    assert len(s.list(2)) == 1 and s.list(3) == []


def test_same_approver_twice_refused():
    s = InMemoryApprovalStore()
    s.add(rec(1, 10))
    with pytest.raises(DuplicateApprovalError):
        s.add(rec(1, 10))
    assert len(s.list(1)) == 1
