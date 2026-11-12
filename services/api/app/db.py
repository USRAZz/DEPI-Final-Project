"""Database tables. Migration 0001 creates exactly these (tests/test_migrations.py checks it).

Rules the schema enforces (issue #15):
- Every tenant row carries company_id, and a reference to another row is (company_id, x_id), so a row can
  never point at another company's vendor, user, invoice or account.
- Status, role and language columns only accept the shared contract values (CHECK constraints).
- The api writes every table except `approvals` and `audit_log`; the gateway is their only writer. Those two
  are append-only for everyone (trigger) and row-level security is forced on them.
"""

import os
from datetime import datetime
from decimal import Decimal

from securefin_contracts import (
    ApprovalStatus,
    BankAccountStatus,
    InvoiceSource,
    InvoiceStatus,
    Language,
    RiskLevel,
    Role,
)
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
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
Id = BigInteger().with_variant(Integer, "sqlite")  # BIGINT ids; SQLite only auto-increments INTEGER PRIMARY KEY
Money = Numeric(14, 2)
Timestamp = DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


def _in(table: str, column: str, enum) -> CheckConstraint:
    """CHECK that a text column only holds the values of a shared contract enum."""
    values = ", ".join(f"'{m.value}'" for m in enum)
    return CheckConstraint(f"{column} IN ({values})", name=f"ck_{table}_{column}")


def _tenant_fk(table: str, column: str, target: str) -> ForeignKeyConstraint:
    """(company_id, x_id) -> table(company_id, id): a row can only point at rows of its own company."""
    return ForeignKeyConstraint(["company_id", column], [f"{target}.company_id", f"{target}.id"],
                                name=f"fk_{table}_{column}_same_company")


def _tenant_key(table: str) -> UniqueConstraint:
    return UniqueConstraint("company_id", "id", name=f"uq_{table}_company_id_id")


class CompanyRow(Base):
    __tablename__ = "companies"
    __table_args__ = (_in("companies", "default_language", Language),)
    id: Mapped[int] = mapped_column(Id, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    tax_id: Mapped[str | None] = mapped_column(String(20))
    default_language: Mapped[str] = mapped_column(String(2), default="ar")
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (
        _tenant_key("users"),
        _in("users", "role", Role),
        _in("users", "language", Language),
        CheckConstraint("email LIKE '_%@_%'", name="ck_users_email"),
    )
    id: Mapped[int] = mapped_column(Id, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(2), default="ar")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class VendorRow(Base):
    __tablename__ = "vendors"
    __table_args__ = (_tenant_key("vendors"),)
    id: Mapped[int] = mapped_column(Id, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    tax_id: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class BankAccountRow(Base):
    """The only payment destinations. A new or changed account starts on_hold (never taken from an invoice)."""

    __tablename__ = "bank_accounts"
    __table_args__ = (
        _tenant_key("bank_accounts"),
        _tenant_fk("bank_accounts", "vendor_id", "vendors"),
        _tenant_fk("bank_accounts", "verified_by", "users"),
        _tenant_fk("bank_accounts", "requested_by", "users"),
        _in("bank_accounts", "status", BankAccountStatus),
        CheckConstraint("times_paid >= 0", name="ck_bank_accounts_times_paid"),
    )
    id: Mapped[int] = mapped_column(Id, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    vendor_id: Mapped[int] = mapped_column(Id, index=True)
    bank_name: Mapped[str] = mapped_column(String(120))
    iban: Mapped[str] = mapped_column(String(34))
    status: Mapped[str] = mapped_column(String(20))
    hold_until: Mapped[datetime | None] = mapped_column(Timestamp)
    verified_by: Mapped[int | None] = mapped_column(Id)
    requested_by: Mapped[int | None] = mapped_column(Id)  # who asked for this account
    times_paid: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class InvoiceRow(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        _tenant_key("invoices"),
        _tenant_fk("invoices", "vendor_id", "vendors"),
        _tenant_fk("invoices", "duplicate_of", "invoices"),
        _tenant_fk("invoices", "uploaded_by", "users"),
        _in("invoices", "source", InvoiceSource),
        _in("invoices", "status", InvoiceStatus),
        CheckConstraint("ocr_confidence BETWEEN 0 AND 1", name="ck_invoices_ocr_confidence"),
        # the exact same file cannot be stored twice per company; same vendor + number is only a duplicate signal
        UniqueConstraint("company_id", "file_sha256", name="uq_invoices_company_id_file_sha256"),
        CheckConstraint("length(file_sha256) = 64", name="ck_invoices_file_sha256"),
    )
    id: Mapped[int] = mapped_column(Id, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    vendor_id: Mapped[int | None] = mapped_column(Id)  # NULL until matched to the vendor registry
    source: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(30))
    fields: Mapped[dict | None] = mapped_column(Json)  # InvoiceData from the extractor; untrusted, never a payee
    file_key: Mapped[str] = mapped_column(String(500))  # generated object key, never the client's file name
    file_sha256: Mapped[str] = mapped_column(String(64))  # sha256 of the file bytes, lowercase hex
    duplicate_of: Mapped[int | None] = mapped_column(Id)
    category: Mapped[str | None] = mapped_column(String(64))
    uploaded_by: Mapped[int | None] = mapped_column(Id)
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    extraction_issues: Mapped[list] = mapped_column(Json, default=list)
    ocr_confidence: Mapped[float | None] = mapped_column(Float)


class InvoiceLineItemRow(Base):
    """The invoice's items as NUMERIC rows (fields.line_items stays the extractor's raw output)."""

    __tablename__ = "invoice_line_items"
    __table_args__ = (
        ForeignKeyConstraint(["company_id", "invoice_id"], ["invoices.company_id", "invoices.id"],
                             name="fk_invoice_line_items_invoice_id_same_company", ondelete="CASCADE"),
        UniqueConstraint("invoice_id", "position", name="uq_invoice_line_items_invoice_id_position"),
        CheckConstraint("position >= 1", name="ck_invoice_line_items_position"),
        CheckConstraint("quantity > 0", name="ck_invoice_line_items_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_invoice_line_items_unit_price"),
    )
    id: Mapped[int] = mapped_column(Id, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    invoice_id: Mapped[int] = mapped_column(Id, index=True)
    position: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    unit_price: Mapped[Decimal] = mapped_column(Money)


class PaymentRequestRow(Base):
    __tablename__ = "payment_requests"
    __table_args__ = (
        _tenant_key("payment_requests"),
        _tenant_fk("payment_requests", "invoice_id", "invoices"),
        _tenant_fk("payment_requests", "vendor_id", "vendors"),
        _tenant_fk("payment_requests", "bank_account_id", "bank_accounts"),
        _tenant_fk("payment_requests", "creator_id", "users"),
        _in("payment_requests", "status", InvoiceStatus),
        CheckConstraint("amount > 0", name="ck_payment_requests_amount_positive"),
        CheckConstraint("length(currency) = 3", name="ck_payment_requests_currency_code"),
    )
    id: Mapped[int] = mapped_column(Id, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    invoice_id: Mapped[int] = mapped_column(Id)
    vendor_id: Mapped[int] = mapped_column(Id)
    bank_account_id: Mapped[int] = mapped_column(Id)
    creator_id: Mapped[int] = mapped_column(Id)
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(30), index=True)
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class PaymentRiskRow(Base):
    """Latest RiskScore for a payment request, as returned by services/risk."""

    __tablename__ = "payment_risk"
    __table_args__ = (
        _in("payment_risk", "level", RiskLevel),
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_payment_risk_score"),
    )
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
    __table_args__ = (
        _tenant_fk("approval_responses", "payment_request_id", "payment_requests"),
        _tenant_fk("approval_responses", "approver_id", "users"),
        _in("approval_responses", "status", ApprovalStatus),
    )
    id: Mapped[int] = mapped_column(Id, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    payment_request_id: Mapped[int] = mapped_column(Id, index=True)
    approver_id: Mapped[int] = mapped_column(Id)
    approve: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(20))
    approvals_received: Mapped[int] = mapped_column(Integer)
    approvals_required: Mapped[int] = mapped_column(Integer)
    reasons: Mapped[list] = mapped_column(Json, default=list)
    at: Mapped[datetime] = mapped_column(Timestamp)


# -- written by the gateway only (issue #15) -----------------------------------------


class ApprovalRow(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint("payment_request_id", "approver_id", name="uq_approvals_one_per_approver"),
        _tenant_fk("approvals", "payment_request_id", "payment_requests"),
        _tenant_fk("approvals", "approver_id", "users"),
        CheckConstraint("expires_at > signed_at", name="ck_approvals_expiry"),
    )
    id: Mapped[int] = mapped_column(Id, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    payment_request_id: Mapped[int] = mapped_column(Id, index=True)
    approver_id: Mapped[int] = mapped_column(Id)
    approve: Mapped[bool] = mapped_column(Boolean)
    hmac_signature: Mapped[str] = mapped_column(String(128))
    signed_at: Mapped[datetime] = mapped_column(Timestamp)
    expires_at: Mapped[datetime] = mapped_column(Timestamp)  # the gateway sets signed_at + 72 h


class AuditLogRow(Base):
    """Columns follow the AuditEntry contract plus company_id. One hash chain per company."""

    __tablename__ = "audit_log"
    __table_args__ = (
        _tenant_fk("audit_log", "user_id", "users"),
        CheckConstraint("prev_hash ~ '^[0-9a-f]{64}$'", name="ck_audit_log_prev_hash").ddl_if(dialect="postgresql"),
        CheckConstraint("entry_hash ~ '^[0-9a-f]{64}$'", name="ck_audit_log_entry_hash").ddl_if(dialect="postgresql"),
    )
    id: Mapped[int] = mapped_column(Id, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(Timestamp, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(Id)
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
