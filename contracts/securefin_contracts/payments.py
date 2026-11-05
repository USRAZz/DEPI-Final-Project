"""Payment requests. Written by services/api; executed only after the gateway allows."""
from datetime import datetime
from enum import Enum

from pydantic import Field

from .common import Contract, Money


class PaymentRequestStatus(str, Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    BLOCKED = "blocked"
    REJECTED = "rejected"
    EXPORTED = "exported"  # included in a bank payment file


class PaymentRequestCreate(Contract):
    """What a user (or the assistant, on the user's behalf) submits. Prepares; never pays."""

    vendor_id: int
    bank_account_id: int
    invoice_ids: list[int] = Field(min_length=1, max_length=50)
    money: Money
    note: str = Field(default="", max_length=500)


class PaymentRequest(Contract):
    id: int
    company_id: int
    vendor_id: int
    bank_account_id: int
    invoice_ids: list[int] = Field(min_length=1, max_length=50)
    money: Money
    note: str = Field(default="", max_length=500)
    status: PaymentRequestStatus
    created_by: int
    created_at: datetime
