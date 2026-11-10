"""Append-only, hash-chained audit log (the gateway is its only writer; GitHub issues #15 and #16).

One chain per company: row-level security means the gateway only sees one company's rows at a time.
entry_hash = SHA256(canonical(entry without id/prev_hash/entry_hash) + prev_hash); the first prev_hash is
GENESIS. verify() re-reads the chain and returns the index of the first broken entry (None = intact).
"""
import json
import threading
from datetime import UTC, datetime

from securefin_contracts import AuditEntry, AuditEvent
from sqlalchemy import Engine, text

from .audit_chain import GENESIS, compute_hash, verify_chain
from .db import tenant_tx

_COLUMNS = ("timestamp", "company_id", "user_id", "action", "tool_call", "parameters", "decision", "risk_level",
            "result", "source_service")


def _hashed(event: AuditEvent, timestamp: datetime, prev_hash: str) -> AuditEntry:
    draft = AuditEntry(id=0, timestamp=timestamp, prev_hash=prev_hash, entry_hash="", **event.model_dump())
    data = draft.model_dump(mode="json", exclude={"id", "prev_hash", "entry_hash"})
    return draft.model_copy(update={"entry_hash": compute_hash(data, prev_hash)})


def first_broken(entries: list[AuditEntry]) -> int | None:
    """Index of the first entry that breaks the chain; None when the chain is intact."""
    return verify_chain([e.model_dump(mode="json", exclude={"id"}) for e in entries])


class InMemoryAuditLog:
    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._lock = threading.Lock()

    def append(self, event: AuditEvent) -> AuditEntry:
        with self._lock:
            chain = self.entries(event.company_id)
            entry = _hashed(event, datetime.now(UTC), chain[-1].entry_hash if chain else GENESIS)
            entry = entry.model_copy(update={"id": len(self._entries) + 1})
            self._entries.append(entry)
            return entry

    def entries(self, company_id: int | None) -> list[AuditEntry]:
        return [e for e in self._entries if e.company_id == company_id]

    def verify(self, company_id: int | None) -> int | None:
        return first_broken(self.entries(company_id))


class PostgresAuditLog:
    def __init__(self, engine: Engine):
        self.engine = engine

    def append(self, event: AuditEvent) -> AuditEntry:
        if event.company_id is None:
            raise ValueError("audit_log rows need a company_id")
        with tenant_tx(self.engine, event.company_id) as c:
            # One writer at a time per company, so two requests cannot both chain onto the same prev_hash.
            c.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": event.company_id})
            prev = c.execute(text("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1")).scalar()
            entry = _hashed(event, datetime.now(UTC), prev or GENESIS)
            row = entry.model_dump(include=set(_COLUMNS) | {"prev_hash", "entry_hash"})
            row["parameters"] = json.dumps(row["parameters"], default=str)
            values = ", ".join("CAST(:parameters AS jsonb)" if k == "parameters" else f":{k}" for k in row)
            new_id = c.execute(text(f"INSERT INTO audit_log ({', '.join(row)}) VALUES ({values}) RETURNING id"),
                               row).scalar()
            return entry.model_copy(update={"id": new_id})

    def entries(self, company_id: int) -> list[AuditEntry]:
        with tenant_tx(self.engine, company_id) as c:
            rows = c.execute(text(f"SELECT id, {', '.join(_COLUMNS)}, prev_hash, entry_hash "
                                  "FROM audit_log ORDER BY id")).mappings()
            return [AuditEntry(**r) for r in rows]

    def verify(self, company_id: int) -> int | None:
        return first_broken(self.entries(company_id))
