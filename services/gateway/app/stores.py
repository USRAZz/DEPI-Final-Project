"""Where signed approvals are kept.

`ApprovalStore` is the interface. `InMemoryApprovalStore` is for local runs and tests (lost on restart);
`PostgresApprovalStore` uses the `approvals` table (migration 0001) (GitHub issue #15). company_id selects
the tenant for row-level security; the in-memory store ignores it.
"""
import threading
from datetime import timedelta
from typing import Protocol

from securefin_contracts import ApprovalRecord
from sqlalchemy import Engine, exc, text

from .db import tenant_tx


class DuplicateApprovalError(RuntimeError):
    """This approver already has a record for this payment request."""


class ApprovalStore(Protocol):
    def list(self, payment_request_id: int, company_id: int | None = None) -> list[ApprovalRecord]: ...

    def add(self, record: ApprovalRecord, company_id: int | None = None) -> None: ...


class InMemoryApprovalStore:
    def __init__(self) -> None:
        self._records: list[ApprovalRecord] = []
        self._lock = threading.Lock()

    def list(self, payment_request_id: int, company_id: int | None = None) -> list[ApprovalRecord]:
        with self._lock:
            return [r for r in self._records if r.payment_request_id == payment_request_id]

    def add(self, record: ApprovalRecord, company_id: int | None = None) -> None:
        with self._lock:
            if any(r.payment_request_id == record.payment_request_id and r.approver_id == record.approver_id
                   for r in self._records):
                raise DuplicateApprovalError(record.approver_id)
            self._records.append(record)


class PostgresApprovalStore:
    """The UNIQUE (payment_request_id, approver_id) constraint makes a second vote fail even under races."""

    def __init__(self, engine: Engine, expiry_hours: int):
        self.engine, self.expiry = engine, timedelta(hours=expiry_hours)

    def list(self, payment_request_id: int, company_id: int | None = None) -> list[ApprovalRecord]:
        with tenant_tx(self.engine, _required(company_id)) as c:
            rows = c.execute(text("SELECT payment_request_id, approver_id, approve, hmac_signature, signed_at "
                                  "FROM approvals WHERE payment_request_id = :p ORDER BY id"),
                             {"p": payment_request_id}).mappings()
            return [ApprovalRecord(**r) for r in rows]

    def add(self, record: ApprovalRecord, company_id: int | None = None) -> None:
        try:
            with tenant_tx(self.engine, _required(company_id)) as c:
                c.execute(text("INSERT INTO approvals (company_id, payment_request_id, approver_id, approve, "
                               "hmac_signature, signed_at, expires_at) VALUES (:c, :p, :a, :ok, :sig, :at, :exp)"),
                          {"c": company_id, "p": record.payment_request_id, "a": record.approver_id,
                           "ok": record.approve, "sig": record.hmac_signature, "at": record.signed_at,
                           "exp": record.signed_at + self.expiry})
        except exc.IntegrityError as e:
            if getattr(e.orig, "sqlstate", None) == "23505":  # unique_violation
                raise DuplicateApprovalError(record.approver_id) from None
            raise


def _required(company_id: int | None) -> int:
    if company_id is None:  # without a tenant, row-level security would hide everything: refuse instead
        raise ValueError("company_id is required for the database store")
    return company_id
