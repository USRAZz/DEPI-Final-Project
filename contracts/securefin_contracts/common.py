from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


class Role(str, Enum):
    VIEWER = "viewer"
    ACCOUNTANT = "accountant"
    APPROVER = "approver"
    ADMIN = "admin"


class Decision(str, Enum):
    ALLOW = "ALLOW"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    BLOCK = "BLOCK"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class InvoiceStatus(str, Enum):
    VALIDATED = "VALIDATED"
    NEEDS_REVIEW = "NEEDS-REVIEW"
    FLAGGED = "FLAGGED"
    VENDOR_CHANGE_PENDING = "VENDOR_CHANGE_PENDING"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    PAID_SIMULATED = "PAID_SIMULATED"
    REJECTED = "REJECTED"


class ApprovalStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class Contract(BaseModel):
    """Base for stored records: an unknown field is an error, so a typo or an injected field never slips through."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Language(str, Enum):
    AR = "ar"
    EN = "en"


class Currency(str, Enum):
    EGP = "EGP"
    USD = "USD"
    EUR = "EUR"


# Money is always Decimal, never float. Two decimal places, never negative.
Amount = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


class Money(Contract):
    amount: Amount
    currency: Currency = Currency.EGP


def _normalize_eg_iban(value: str) -> str:
    iban = value.replace(" ", "").upper()
    # Egyptian IBAN: EG + 2 check digits + 25 digits = 29 characters.
    if len(iban) != 29 or not iban.startswith("EG") or not iban[2:].isdigit():
        raise ValueError("must be an Egyptian IBAN: EG followed by 27 digits")
    rearranged = iban[4:] + "1416" + iban[2:4]  # E=14, G=16
    if int(rearranged) % 97 != 1:
        raise ValueError("IBAN check digits are invalid")
    return iban


EgyptianIBAN = Annotated[str, AfterValidator(_normalize_eg_iban)]
