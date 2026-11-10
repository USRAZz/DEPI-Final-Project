"""Shared contracts for SecureFin AI. Every service imports types from here — never redefine them."""
from .actions import ChatRequest, ChatResponse, ProposedAction, ToolName
from .audit import AuditEntry, AuditEvent
from .common import (
    ApprovalStatus,
    Contract,
    Currency,
    Decision,
    EgyptianIBAN,
    InvoiceStatus,
    Language,
    Money,
    RiskLevel,
    Role,
)
from .companies import Company, User
from .gateway import (
    ApprovalRecord,
    ApprovalRequest,
    ApprovalResult,
    AuthorizeRequest,
    ExecuteCheckRequest,
    ExecuteCheckResult,
    GatewayDecision,
    PaymentRequestInfo,
)
from .invoice import ExtractResponse, Invoice, InvoiceData, InvoiceSource, LineItem
from .risk import RiskFeatures, RiskRequest, RiskScore, ShapReason
from .vendors import BankAccount, BankAccountChangeRequest, BankAccountStatus, Vendor

__version__ = "0.1.0"
__all__ = [
    "Role", "Decision", "RiskLevel", "InvoiceStatus", "ApprovalStatus",
    "LineItem", "InvoiceData", "ExtractResponse",
    "ToolName", "ProposedAction", "ChatRequest", "ChatResponse",
    "AuthorizeRequest", "GatewayDecision", "ApprovalRequest", "ApprovalRecord",
    "PaymentRequestInfo", "ApprovalResult", "ExecuteCheckRequest", "ExecuteCheckResult",
    "RiskFeatures", "RiskRequest", "RiskScore", "ShapReason",
    "AuditEvent", "AuditEntry",
    "Contract", "Currency", "EgyptianIBAN", "Language", "Money",
    "Company", "User",
    "Vendor", "BankAccount", "BankAccountStatus", "BankAccountChangeRequest",
    "Invoice", "InvoiceSource",
]
