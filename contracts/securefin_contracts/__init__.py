"""Shared contracts for SecureFin AI. Every service imports types from here — never redefine them."""
from .actions import ChatRequest, ChatResponse, ChatTurn, InvoiceAlert, ProposedAction, ToolName
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
from .reports import Report, ReportRequest, ReportSection, ReportSectionKey
from .risk import (
    ExplainRequest,
    RiskExplanation,
    RiskFeatures,
    RiskReason,
    RiskRequest,
    RiskScore,
    ShapReason,
)
from .vendors import BankAccount, BankAccountChangeRequest, BankAccountStatus, Vendor

__version__ = "0.1.0"
__all__ = [
    "Role", "Decision", "RiskLevel", "InvoiceStatus", "ApprovalStatus",
    "LineItem", "InvoiceData", "ExtractResponse",
    "ToolName", "ProposedAction", "ChatRequest", "ChatResponse", "ChatTurn", "InvoiceAlert",
    "AuthorizeRequest", "GatewayDecision", "ApprovalRequest", "ApprovalRecord",
    "PaymentRequestInfo", "ApprovalResult", "ExecuteCheckRequest", "ExecuteCheckResult",
    "RiskFeatures", "RiskRequest", "RiskScore", "ShapReason", "ExplainRequest", "RiskExplanation", "RiskReason",
    "AuditEvent", "AuditEntry",
    "Report", "ReportRequest", "ReportSection", "ReportSectionKey",
    "Contract", "Currency", "EgyptianIBAN", "Language", "Money",
    "Company", "User",
    "Vendor", "BankAccount", "BankAccountStatus", "BankAccountChangeRequest",
    "Invoice", "InvoiceSource",
]
