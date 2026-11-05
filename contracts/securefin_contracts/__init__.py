"""Shared contracts for SecureFin AI. Every service imports types from here — never redefine them."""
from .actions import ChatRequest, ChatResponse, ProposedAction, ToolName
from .audit import AuditEntry, AuditEvent
from .common import Contract, Currency, Decision, EgyptianIBAN, InvoiceStatus, Language, Money, RiskLevel, Role
from .companies import Company, User
from .gateway import ApprovalPayload, ApprovalRecord, ApprovalRequest, AuthorizeRequest, GatewayDecision
from .invoice import Invoice, InvoiceData, InvoiceSource, LineItem
from .payments import PaymentRequest, PaymentRequestCreate, PaymentRequestStatus
from .risk import RiskRequest, RiskScore, ShapReason
from .vendors import BankAccount, BankAccountChangeRequest, BankAccountStatus, Vendor

__version__ = "0.1.0"
__all__ = [
    "Role", "Decision", "RiskLevel", "InvoiceStatus",
    "LineItem", "InvoiceData",
    "ToolName", "ProposedAction", "ChatRequest", "ChatResponse",
    "AuthorizeRequest", "GatewayDecision", "ApprovalRequest", "ApprovalRecord",
    "RiskRequest", "RiskScore", "ShapReason",
    "AuditEvent", "AuditEntry",
    "Contract", "Currency", "EgyptianIBAN", "Language", "Money",
    "Company", "User",
    "Vendor", "BankAccount", "BankAccountStatus", "BankAccountChangeRequest",
    "Invoice", "InvoiceSource",
    "PaymentRequest", "PaymentRequestCreate", "PaymentRequestStatus",
    "ApprovalPayload",
]
