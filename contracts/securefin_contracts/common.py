from enum import Enum


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
