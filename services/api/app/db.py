"""Database tables. The Alembic migrations in migrations/versions create exactly these.

The api writes every table here except `approvals` and `audit_log`: the gateway is their only
writer (issue #15). Those two are append-only (trigger in 0001) and gateway-only with row-level security (0002).
"""

import os
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

Json = JSON().with_variant(JSONB(), "postgresql")
Money = Numeric(14, 2)
Timestamp = DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


class CompanyRow(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    tax_id: Mapped[str | None] = mapped_column(String(20))
    default_language: Mapped[str] = mapped_column(String(2), default="ar")
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(2), default="ar")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class VendorRow(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    tax_id: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class BankAccountRow(Base):
    __tablename__ = "bank_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    bank_name: Mapped[str] = mapped_column(String(120))
    iban: Mapped[str] = mapped_column(String(34))
    status: Mapped[str] = mapped_column(String(20))
    hold_until: Mapped[datetime | None] = mapped_column(Timestamp)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # who asked for this account
    times_paid: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class InvoiceRow(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"))
    source: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(30))
    fields: Mapped[dict | None] = mapped_column(Json)  # InvoiceData from the extractor
    file_key: Mapped[str] = mapped_column(String(500))
    duplicate_of: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"))
    category: Mapped[str | None] = mapped_column(String(64))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    extraction_issues: Mapped[list] = mapped_column(Json, default=list)
    ocr_confidence: Mapped[float | None] = mapped_column(Float)


class PaymentRequestRow(Base):
    __tablename__ = "payment_requests"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_requests_amount_positive"),
        CheckConstraint("length(currency) = 3", name="ck_payment_requests_currency_code"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    bank_account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id"))
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(30), index=True)
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class PaymentRiskRow(Base):
    """Latest RiskScore for a payment request, as returned by services/risk."""

    __tablename__ = "payment_risk"
    payment_request_id: Mapped[int] = mapped_column(ForeignKey("payment_requests.id"), primary_key=True)
    score: Mapped[float] = mapped_column(Float)
    level: Mapped[str] = mapped_column(String(10))
    rule_hits: Mapped[list] = mapped_column(Json, default=list)
    shap_reasons: Mapped[list] = mapped_column(Json, default=list)
    model_version: Mapped[str] = mapped_column(String(40))


class ApprovalResponseRow(Base):
    """Each answer the gateway gave the api for an approve/reject, kept for the screens.

    Not an approval record: the signed approvals live in `approvals`, written by the gateway.
    """

    __tablename__ = "approval_responses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    payment_request_id: Mapped[int] = mapped_column(ForeignKey("payment_requests.id"), index=True)
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approve: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(20))
    approvals_received: Mapped[int] = mapped_column(Integer)
    approvals_required: Mapped[int] = mapped_column(Integer)
    reasons: Mapped[list] = mapped_column(Json, default=list)
    at: Mapped[datetime] = mapped_column(Timestamp)


# -- written by the gateway only (issue #15) -----------------------------------------


class ApprovalRow(Base):
    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("payment_request_id", "approver_id", name="uq_approvals_one_per_approver"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)  # 0002: row-level security
    payment_request_id: Mapped[int] = mapped_column(ForeignKey("payment_requests.id"), index=True)
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approve: Mapped[bool] = mapped_column(Boolean)
    hmac_signature: Mapped[str] = mapped_column(String(128))
    signed_at: Mapped[datetime] = mapped_column(Timestamp)
    expires_at: Mapped[datetime] = mapped_column(Timestamp)


class AuditLogRow(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(Timestamp, index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100))
    tool_call: Mapped[str | None] = mapped_column(String(100))
    parameters: Mapped[dict] = mapped_column(Json, default=dict)  # already masked by the caller
    decision: Mapped[str | None] = mapped_column(String(30))
    risk_level: Mapped[str | None] = mapped_column(String(10))
    result: Mapped[str | None] = mapped_column(String(200))
    source_service: Mapped[str] = mapped_column(String(40))
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64), unique=True)


def normalize_url(url: str) -> str:
    """Neon and Vercel hand out postgres:// or postgresql:// URLs; SQLAlchemy needs the psycopg driver named."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def make_engine(url: str) -> Engine:
    url = normalize_url(url)
    # pool_pre_ping: serverless databases (Neon) close idle connections.
    if os.environ.get("VERCEL"):
        # Many short-lived function instances: hold no idle connections and let the database's
        # own pooler (Neon's "-pooler" host) share them.
        return create_engine(url, pool_pre_ping=True, poolclass=NullPool)
    return create_engine(url, pool_pre_ping=True)
