"""Where signed approvals are kept.

`ApprovalStore` is the interface. `InMemoryApprovalStore` is the skeleton implementation (lost on restart);
the database-backed store replaces it once the `approvals` table migration exists.
"""
import threading
from typing import Protocol

from securefin_contracts import ApprovalRecord


class DuplicateApprovalError(RuntimeError):
    """This approver already has a record for this payment request."""


class ApprovalStore(Protocol):
    def list(self, payment_request_id: int) -> list[ApprovalRecord]: ...

    def add(self, record: ApprovalRecord) -> None: ...


class InMemoryApprovalStore:
    def __init__(self) -> None:
        self._records: list[ApprovalRecord] = []
        self._lock = threading.Lock()

    def list(self, payment_request_id: int) -> list[ApprovalRecord]:
        with self._lock:
            return [r for r in self._records if r.payment_request_id == payment_request_id]

    def add(self, record: ApprovalRecord) -> None:
        with self._lock:
            if any(r.payment_request_id == record.payment_request_id and r.approver_id == record.approver_id
                   for r in self._records):
                raise DuplicateApprovalError(record.approver_id)
            self._records.append(record)
