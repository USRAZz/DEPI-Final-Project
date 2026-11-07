"""Gateway contracts (draft v0.1).

Rules:
- Add fields, never rename or remove them.
- Enum values are stable strings; other services depend on them.
- Changed only in a pull request that touches contracts/ alone,
  approved by all four owners.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Role(str, Enum):
    VIEWER = "viewer"
    ACCOUNTANT = "accountant"
    APPROVER = "approver"
    ADMIN = "admin"


class ActorType(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"  # acts on behalf of a user, never final


class Action(str, Enum):
    CREATE_PAYMENT_REQUEST = "create_payment_request"
    APPROVE_PAYMENT = "approve_payment"
    EXECUTE_PAYMENT = "execute_payment"
    CHANGE_VENDOR_BANK_DETAILS = "change_vendor_bank_details"
    CONFIRM_BANK_CHANGE = "confirm_bank_change"
    EXPORT_PAYMENT_FILE = "export_payment_file"
    READ_AUDIT_LOG = "read_audit_log"
    VERIFY_AUDIT_LOG = "verify_audit_log"


class Outcome(str, Enum):
    ALLOW = "allow"
    HOLD = "hold"
    BLOCK = "block"


class ReasonCode(str, Enum):
    OK = "OK"
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_AUTHENTICATED = "NOT_AUTHENTICATED"
    ROLE_DENIED = "ROLE_DENIED"
    COMPANY_MISMATCH = "COMPANY_MISMATCH"
    ACTION_NOT_ALLOWED_FOR_ACTOR = "ACTION_NOT_ALLOWED_FOR_ACTOR"
    SELF_APPROVAL = "SELF_APPROVAL"
    DUPLICATE_APPROVER = "DUPLICATE_APPROVER"
    APPROVAL_PAYLOAD_MISMATCH = "APPROVAL_PAYLOAD_MISMATCH"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVALS_MISSING = "APPROVALS_MISSING"
    NEEDS_SECOND_APPROVER = "NEEDS_SECOND_APPROVER"
    BANK_CHANGE_COOLING = "BANK_CHANGE_COOLING"
    BANK_CHANGE_UNCONFIRMED = "BANK_CHANGE_UNCONFIRMED"
    HIGH_RISK = "HIGH_RISK"
    RISK_UNAVAILABLE = "RISK_UNAVAILABLE"
    GATEWAY_UNAVAILABLE = "GATEWAY_UNAVAILABLE"
    AUDIT_CHAIN_BROKEN = "AUDIT_CHAIN_BROKEN"


class PaymentPayload(BaseModel):
    """The exact details an approver signs. Any change invalidates the approval."""

    model_config = ConfigDict(frozen=True)

    payment_id: UUID
    company_id: UUID
    vendor_id: UUID
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)  # e.g. "EGP"
    bank_account: str  # IBAN or account number, already verified in the vendor directory
    created_by: UUID


class DecisionRequest(BaseModel):
    request_id: UUID
    company_id: UUID
    actor_id: UUID
    actor_type: ActorType = ActorType.USER
    actor_role: Role
    action: Action
    payment: PaymentPayload | None = None
    payload: dict = Field(default_factory=dict)  # action-specific extras; tighten per action later
    risk_score: float | None = Field(default=None, ge=0, le=1)
    requested_at: datetime


class DecisionResponse(BaseModel):
    request_id: UUID
    outcome: Outcome
    reason_codes: list[ReasonCode]
    explanation_key: str  # translation key, never display text
    required_approvers: int = 0
    hold_until: datetime | None = None
    decided_at: datetime


class Approval(BaseModel):
    payment_id: UUID
    company_id: UUID
    approver_id: UUID
    payload_hash: str  # SHA-256 over the canonical PaymentPayload
    signature: str  # base64
    signature_algorithm: str = "ed25519"
    signed_at: datetime
    expires_at: datetime


class AuditEntry(BaseModel):
    seq: int
    company_id: UUID
    request_id: UUID
    actor_id: UUID
    action: Action
    outcome: Outcome
    reason_codes: list[ReasonCode]
    prev_hash: str  # entry_hash of the previous entry ("0"*64 for the first)
    entry_hash: str  # SHA-256 over prev_hash + canonical content
    route: str | None = None  # which flow handled it (invoice, finance_qa, payment, report)
    tools_used: list[str] = Field(default_factory=list)  # tools the assistant called
    created_at: datetime


class AuditVerifyResult(BaseModel):
    ok: bool
    entries_checked: int
    first_broken_seq: int | None = None
    checked_at: datetime
