"""Vendors and their bank accounts. A new or changed account is held before it can be paid."""
from datetime import datetime
from enum import Enum

from pydantic import Field

from .common import Contract, EgyptianIBAN


class Vendor(Contract):
    id: int
    company_id: int
    name: str = Field(min_length=1, max_length=200)
    tax_id: str | None = Field(default=None, max_length=20)
    created_at: datetime


class BankAccountStatus(str, Enum):
    ON_HOLD = "on_hold"  # new or changed; cannot be paid yet
    VERIFIED = "verified"  # hold period passed and confirmed out of band
    REJECTED = "rejected"


class BankAccount(Contract):
    id: int
    company_id: int
    vendor_id: int
    bank_name: str = Field(min_length=1, max_length=120)
    iban: EgyptianIBAN
    status: BankAccountStatus = BankAccountStatus.ON_HOLD
    hold_until: datetime | None = None
    verified_by: int | None = None
    created_at: datetime


class BankAccountChangeRequest(Contract):
    """A request to add or replace a vendor's bank account. Never applied directly."""

    vendor_id: int
    bank_name: str = Field(min_length=1, max_length=120)
    iban: EgyptianIBAN
    requested_by: int
    reason: str = Field(default="", max_length=500)
