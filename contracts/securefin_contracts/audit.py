"""Hash-chained audit log: entry_hash[n] = SHA256(entry_data[n] + entry_hash[n-1]). Only the gateway writes it."""
from datetime import datetime

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    user_id: int | None
    company_id: int | None = None
    action: str = Field(max_length=100)
    tool_call: str | None = None
    parameters: dict = Field(default_factory=dict, description="Already masked by the caller")
    decision: str | None = None
    risk_level: str | None = None
    result: str | None = None
    source_service: str


class AuditEntry(AuditEvent):
    id: int
    timestamp: datetime
    prev_hash: str
    entry_hash: str
