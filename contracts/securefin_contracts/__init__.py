"""Shared contracts for SecureFin AI. Every service imports types from here — never redefine them."""
from .actions import ChatRequest, ChatResponse, ProposedAction, ToolName
from .audit import AuditEntry, AuditEvent
from .common import ApprovalStatus, Decision, InvoiceStatus, RiskLevel, Role
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
from .invoice import InvoiceData, LineItem
from .risk import RiskFeatures, RiskRequest, RiskScore, ShapReason

__version__ = "0.1.0"
__all__ = [
    "Role", "Decision", "RiskLevel", "InvoiceStatus", "ApprovalStatus",
    "LineItem", "InvoiceData",
    "ToolName", "ProposedAction", "ChatRequest", "ChatResponse",
    "AuthorizeRequest", "GatewayDecision", "ApprovalRequest", "ApprovalRecord",
    "PaymentRequestInfo", "ApprovalResult", "ExecuteCheckRequest", "ExecuteCheckResult",
    "RiskFeatures", "RiskRequest", "RiskScore", "ShapReason",
    "AuditEvent", "AuditEntry",
]
