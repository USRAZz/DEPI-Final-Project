"""DataStore on PostgreSQL (SQLite in tests), through the tables in db.py.

Rows are turned into the same contract models the in-memory Store returns, so routes
cannot tell the two apart. Each method is one short transaction.

Reads for one company run as role securefin_app with app.company_id set (migration 0001), so PostgreSQL's
row-level security filters them as well as the WHERE clause. Lookups that come before the company is known
(the signed-in user, service-to-service reads by id) and the sample-data loader use the owner login.
"""
from contextlib import contextmanager
from datetime import UTC, datetime

from securefin_contracts import (
    ApprovalResult,
    ApprovalStatus,
    BankAccount,
    BankAccountStatus,
    Invoice,
    InvoiceStatus,
    RiskScore,
    User,
    Vendor,
)
from sqlalchemy import func, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .db import (
    ApprovalResponseRow,
    BankAccountRow,
    CompanyRow,
    InvoiceLineItemRow,
    InvoiceRow,
    PaymentRequestRow,
    PaymentRiskRow,
    UserRow,
    VendorRow,
)
from .models import PaymentRecord
from .store import ApprovalEntry, Store


def _utc(value):
    # SQLite gives back naive datetimes; everything is stored in UTC.
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _cols(row, *, skip: tuple[str, ...] = ()) -> dict:
    return {c.key: _utc(getattr(row, c.key)) for c in row.__table__.columns if c.key not in skip}


def _user(row: UserRow | None) -> User | None:
    return User.model_validate(_cols(row)) if row else None


def _vendor(row: VendorRow | None) -> Vendor | None:
    return Vendor.model_validate(_cols(row)) if row else None


def _account(row: BankAccountRow | None) -> BankAccount | None:
    return BankAccount.model_validate(_cols(row, skip=("requested_by", "times_paid"))) if row else None


def _invoice(row: InvoiceRow | None) -> Invoice | None:
    return Invoice.model_validate(_cols(row)) if row else None


def _payment(row: PaymentRequestRow | None) -> PaymentRecord | None:
    return PaymentRecord.model_validate(_cols(row)) if row else None


class SqlStore:
    def __init__(self, engine: Engine):
        self._session = sessionmaker(engine, expire_on_commit=False)

    def _one(self, stmt):
        with self._session() as s:
            return s.scalars(stmt).first()

    @contextmanager
    def _tenant(self, company_id: int):
        """A read-only transaction that PostgreSQL limits to one company (no-op on SQLite)."""
        with self._session() as s, s.begin():
            if s.get_bind().dialect.name == "postgresql":
                s.execute(text("SET LOCAL ROLE securefin_app"))
                s.execute(text("SELECT set_config('app.company_id', :c, true)"), {"c": str(company_id)})
            yield s

    def _tenant_one(self, company_id: int, stmt):
        with self._tenant(company_id) as s:
            return s.scalars(stmt).first()

    def _scoped(self, model, item_id: int, company_id: int):
        return self._tenant_one(company_id, select(model).where(model.id == item_id, model.company_id == company_id))

    # -- reads -----------------------------------------------------------------

    def user(self, user_id: int) -> User | None:
        return _user(self._one(select(UserRow).where(UserRow.id == user_id)))

    def vendor(self, vendor_id: int, company_id: int) -> Vendor | None:
        return _vendor(self._scoped(VendorRow, vendor_id, company_id))

    def invoice(self, invoice_id: int, company_id: int) -> Invoice | None:
        return _invoice(self._scoped(InvoiceRow, invoice_id, company_id))

    def invoice_by_id(self, invoice_id: int) -> Invoice | None:
        return _invoice(self._one(select(InvoiceRow).where(InvoiceRow.id == invoice_id)))

    def payment_request(self, request_id: int, company_id: int) -> PaymentRecord | None:
        return _payment(self._scoped(PaymentRequestRow, request_id, company_id))

    def payment_request_by_id(self, request_id: int) -> PaymentRecord | None:
        return _payment(self._one(select(PaymentRequestRow).where(PaymentRequestRow.id == request_id)))

    def bank_account(self, account_id: int, company_id: int) -> BankAccount | None:
        return _account(self._scoped(BankAccountRow, account_id, company_id))

    def vendor_accounts(self, vendor_id: int, company_id: int) -> list[BankAccount]:
        with self._tenant(company_id) as s:
            rows = s.scalars(select(BankAccountRow).where(
                BankAccountRow.vendor_id == vendor_id, BankAccountRow.company_id == company_id,
            ).order_by(BankAccountRow.id))
            return [_account(r) for r in rows]

    def times_paid(self, account_id: int) -> int:
        return self._one(select(BankAccountRow.times_paid).where(BankAccountRow.id == account_id)) or 0

    def bank_change_requester(self, vendor_id: int) -> User | None:
        user_id = self._one(select(BankAccountRow.requested_by).where(
            BankAccountRow.vendor_id == vendor_id, BankAccountRow.status == BankAccountStatus.ON_HOLD.value,
            BankAccountRow.requested_by.is_not(None)))
        return self.user(user_id) if user_id is not None else None

    def pending_requests(self, company_id: int) -> list[PaymentRecord]:
        with self._tenant(company_id) as s:
            rows = s.scalars(select(PaymentRequestRow).where(
                PaymentRequestRow.company_id == company_id,
                PaymentRequestRow.status == InvoiceStatus.PENDING_APPROVAL.value,
            ).order_by(PaymentRequestRow.created_at))
            return [_payment(r) for r in rows]

    def flagged_invoice_count(self, company_id: int) -> int:
        return self._tenant_one(company_id, select(func.count()).select_from(InvoiceRow).where(
            InvoiceRow.company_id == company_id, InvoiceRow.status == InvoiceStatus.FLAGGED.value))

    def on_hold_account_count(self, company_id: int) -> int:
        return self._tenant_one(company_id, select(func.count()).select_from(BankAccountRow).where(
            BankAccountRow.company_id == company_id, BankAccountRow.status == BankAccountStatus.ON_HOLD.value))

    def risk(self, request_id: int) -> RiskScore | None:
        row = self._one(select(PaymentRiskRow).where(PaymentRiskRow.payment_request_id == request_id))
        return RiskScore.model_validate(_cols(row, skip=("payment_request_id",))) if row else None

    def approvals(self, request_id: int) -> list[ApprovalEntry]:
        with self._session() as s:
            rows = s.scalars(select(ApprovalResponseRow).where(
                ApprovalResponseRow.payment_request_id == request_id,
                ApprovalResponseRow.status != ApprovalStatus.EXPIRED.value,
            ).order_by(ApprovalResponseRow.id))
            return [ApprovalEntry(approver_id=r.approver_id, approve=r.approve, at=_utc(r.at)) for r in rows]

    def approval_result(self, request_id: int) -> ApprovalResult | None:
        row = self._one(select(ApprovalResponseRow).where(ApprovalResponseRow.payment_request_id == request_id)
                        .order_by(ApprovalResponseRow.id.desc()))
        if row is None:
            return None
        return ApprovalResult(payment_request_id=request_id, status=row.status, reasons=row.reasons,
                              approvals_received=row.approvals_received, approvals_required=row.approvals_required)

    # -- writes ----------------------------------------------------------------

    def set_request_status(self, request_id: int, status: InvoiceStatus) -> None:
        with self._session.begin() as s:
            s.execute(update(PaymentRequestRow).where(PaymentRequestRow.id == request_id).values(status=status.value))

    def record_approval(self, approver_id: int, approve: bool, result: ApprovalResult) -> None:
        with self._session.begin() as s:
            company_id = s.scalar(select(PaymentRequestRow.company_id)
                                  .where(PaymentRequestRow.id == result.payment_request_id))
            s.add(ApprovalResponseRow(
                company_id=company_id, payment_request_id=result.payment_request_id, approver_id=approver_id,
                approve=approve, status=result.status.value, approvals_received=result.approvals_received,
                approvals_required=result.approvals_required, reasons=result.reasons, at=datetime.now(UTC),
            ))

    def mark_paid(self, request_id: int) -> PaymentRecord:
        """PAID_SIMULATED and one more payment to that account, in one transaction."""
        with self._session.begin() as s:
            row = s.get(PaymentRequestRow, request_id, with_for_update=True)
            row.status = InvoiceStatus.PAID_SIMULATED.value
            s.execute(update(BankAccountRow).where(BankAccountRow.id == row.bank_account_id)
                      .values(times_paid=BankAccountRow.times_paid + 1))
            return _payment(row)

    def set_account_status(self, account_id: int, status: BankAccountStatus) -> None:
        with self._session.begin() as s:
            s.execute(update(BankAccountRow).where(BankAccountRow.id == account_id).values(status=status.value))

    # -- loading ---------------------------------------------------------------

    def is_empty(self) -> bool:
        return not self._one(select(func.count()).select_from(CompanyRow))

    def load(self, data: Store) -> None:
        """Insert everything in an in-memory Store, e.g. the sample data, in one transaction."""
        with self._session.begin() as s:
            _insert_all(s, data)
            if s.get_bind().dialect.name == "postgresql":
                # rows came with their own ids: move each id sequence past them so new rows do not collide
                for table in ("companies", "users", "vendors", "bank_accounts", "invoices", "invoice_line_items",
                              "payment_requests"):
                    s.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                                   f"(SELECT coalesce(max(id), 0) + 1 FROM {table}), false)"))


def _line_items(inv: Invoice) -> list[InvoiceLineItemRow]:
    """The extractor's line items as NUMERIC rows, numbered from 1 in document order."""
    items = inv.fields.line_items if inv.fields else []
    return [InvoiceLineItemRow(company_id=inv.company_id, invoice_id=inv.id, position=n, description=item.description,
                               quantity=item.quantity, unit_price=item.unit_price)
            for n, item in enumerate(items, start=1)]


def _insert_all(s: Session, data: Store) -> None:
    def dumped(model, **extra) -> dict:
        return {**model.model_dump(mode="python"), **extra}

    s.add_all(CompanyRow(**dumped(c, default_language=c.default_language.value)) for c in data.companies.values())
    s.add_all(UserRow(**dumped(u, role=u.role.value, language=u.language.value)) for u in data.users.values())
    s.add_all(VendorRow(**dumped(v)) for v in data.vendors.values())
    s.flush()
    requested_by = {vendor_id: user_id for vendor_id, user_id in data.bank_change_requested_by.items()}
    s.add_all(BankAccountRow(
        **dumped(a, status=a.status.value), times_paid=data.times_paid(a.id),
        requested_by=requested_by.get(a.vendor_id) if a.status == BankAccountStatus.ON_HOLD else None,
    ) for a in data.bank_accounts.values())
    for inv in sorted(data.invoices.values(), key=lambda i: i.id):  # an invoice can point to an earlier one
        s.add(InvoiceRow(**{**inv.model_dump(mode="json"), "created_at": inv.created_at}))
        s.flush()
        s.add_all(_line_items(inv))
    s.add_all(PaymentRequestRow(**dumped(p, status=p.status.value)) for p in data.payment_requests.values())
    s.flush()
    s.add_all(PaymentRiskRow(payment_request_id=rid, **r.model_dump(mode="json"))
              for rid, r in data.risks.items())
