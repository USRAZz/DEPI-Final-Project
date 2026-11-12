"""The data store the routes use, and an in-memory implementation with sample data.

DataStore is the interface; Store keeps everything in memory (local runs without a
database, and fast tests) and SqlStore in sql_store.py keeps it in PostgreSQL.
Every company-facing lookup takes the caller's company_id: a record from another
company is "not found", never "forbidden", so its existence does not leak.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol, TypeVar

from securefin_contracts import (
    ApprovalResult,
    ApprovalStatus,
    BankAccount,
    BankAccountStatus,
    Company,
    Invoice,
    InvoiceData,
    InvoiceSource,
    InvoiceStatus,
    RiskLevel,
    RiskScore,
    Role,
    ShapReason,
    User,
    Vendor,
)

from .models import PaymentRecord

T = TypeVar("T")

# Sample record ids, so links and tests survive restarts.
DELTA, OTHER = 1, 2
KARIM, MONA, SARA, OMAR, VIEWER, OUTSIDER = 1, 2, 3, 4, 5, 6
NILE, EGPACK, CAIRONET, AMAL = 1, 2, 3, 4
ACC_NILE, ACC_EGPACK_OLD, ACC_EGPACK_NEW, ACC_CAIRONET, ACC_AMAL = 1, 2, 3, 4, 5
INV_0412, INV_0371 = 412, 371
PR_187, PR_188, PR_189, PR_190 = 187, 188, 189, 190


def _at(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=UTC)


@dataclass(frozen=True)
class ApprovalEntry:
    approver_id: int
    approve: bool
    at: datetime


class DataStore(Protocol):
    def user(self, user_id: int) -> User | None: ...
    def vendor(self, vendor_id: int, company_id: int) -> Vendor | None: ...
    def invoice(self, invoice_id: int, company_id: int) -> Invoice | None: ...
    def invoice_by_id(self, invoice_id: int) -> Invoice | None: ...  # trusted internal callers only
    def payment_request(self, request_id: int, company_id: int) -> PaymentRecord | None: ...
    def payment_request_by_id(self, request_id: int) -> PaymentRecord | None: ...  # trusted internal callers only
    def bank_account(self, account_id: int, company_id: int) -> BankAccount | None: ...
    def vendor_accounts(self, vendor_id: int, company_id: int) -> list[BankAccount]: ...
    def times_paid(self, account_id: int) -> int: ...
    def bank_change_requester(self, vendor_id: int) -> User | None: ...
    def pending_requests(self, company_id: int) -> list[PaymentRecord]: ...
    def flagged_invoice_count(self, company_id: int) -> int: ...
    def on_hold_account_count(self, company_id: int) -> int: ...
    def risk(self, request_id: int) -> RiskScore | None: ...
    def approvals(self, request_id: int) -> list[ApprovalEntry]: ...
    def approval_result(self, request_id: int) -> ApprovalResult | None: ...
    def set_request_status(self, request_id: int, status: InvoiceStatus) -> None: ...
    def record_approval(self, approver_id: int, approve: bool, result: ApprovalResult) -> None: ...
    def mark_paid(self, request_id: int) -> PaymentRecord: ...
    def set_account_status(self, account_id: int, status: BankAccountStatus) -> None: ...


@dataclass
class Store:
    companies: dict[int, Company] = field(default_factory=dict)
    users: dict[int, User] = field(default_factory=dict)
    vendors: dict[int, Vendor] = field(default_factory=dict)
    bank_accounts: dict[int, BankAccount] = field(default_factory=dict)
    paid_counts: dict[int, int] = field(default_factory=dict)
    invoices: dict[int, Invoice] = field(default_factory=dict)
    payment_requests: dict[int, PaymentRecord] = field(default_factory=dict)
    risks: dict[int, RiskScore] = field(default_factory=dict)
    bank_change_requested_by: dict[int, int] = field(default_factory=dict)
    # What the gateway answered, kept for the screens: the gateway has no read endpoint for approvals.
    approval_entries: dict[int, list[ApprovalEntry]] = field(default_factory=dict)
    approval_results: dict[int, ApprovalResult] = field(default_factory=dict)

    # -- reads -----------------------------------------------------------------

    def user(self, user_id: int) -> User | None:
        return self.users.get(user_id)

    def invoice_by_id(self, invoice_id: int) -> Invoice | None:
        return self.invoices.get(invoice_id)

    def payment_request_by_id(self, request_id: int) -> PaymentRecord | None:
        return self.payment_requests.get(request_id)

    def times_paid(self, account_id: int) -> int:
        return self.paid_counts.get(account_id, 0)

    def bank_change_requester(self, vendor_id: int) -> User | None:
        user_id = self.bank_change_requested_by.get(vendor_id)
        return self.users.get(user_id) if user_id is not None else None

    def risk(self, request_id: int) -> RiskScore | None:
        return self.risks.get(request_id)

    def approvals(self, request_id: int) -> list[ApprovalEntry]:
        return list(self.approval_entries.get(request_id, []))

    def approval_result(self, request_id: int) -> ApprovalResult | None:
        return self.approval_results.get(request_id)

    def _scoped(self, table: dict[int, T], item_id: int, company_id: int) -> T | None:
        item = table.get(item_id)
        return item if item is not None and item.company_id == company_id else None

    def vendor(self, vendor_id: int, company_id: int) -> Vendor | None:
        return self._scoped(self.vendors, vendor_id, company_id)

    def invoice(self, invoice_id: int, company_id: int) -> Invoice | None:
        return self._scoped(self.invoices, invoice_id, company_id)

    def payment_request(self, request_id: int, company_id: int) -> PaymentRecord | None:
        return self._scoped(self.payment_requests, request_id, company_id)

    def bank_account(self, account_id: int, company_id: int) -> BankAccount | None:
        return self._scoped(self.bank_accounts, account_id, company_id)

    def vendor_accounts(self, vendor_id: int, company_id: int) -> list[BankAccount]:
        return [a for a in self.bank_accounts.values() if a.vendor_id == vendor_id and a.company_id == company_id]

    def pending_requests(self, company_id: int) -> list[PaymentRecord]:
        return sorted(
            (p for p in self.payment_requests.values()
             if p.company_id == company_id and p.status == InvoiceStatus.PENDING_APPROVAL),
            key=lambda p: p.created_at,
        )

    def flagged_invoice_count(self, company_id: int) -> int:
        return sum(1 for i in self.invoices.values() if i.company_id == company_id and i.status == InvoiceStatus.FLAGGED)

    def on_hold_account_count(self, company_id: int) -> int:
        return sum(1 for a in self.bank_accounts.values()
                   if a.company_id == company_id and a.status == BankAccountStatus.ON_HOLD)

    def set_request_status(self, request_id: int, status: InvoiceStatus) -> None:
        self.payment_requests[request_id] = self.payment_requests[request_id].model_copy(update={"status": status})

    def record_approval(self, approver_id: int, approve: bool, result: ApprovalResult) -> None:
        # On EXPIRED the gateway stores nothing, so the screens must not list this approval either.
        if result.status != ApprovalStatus.EXPIRED:
            self.approval_entries.setdefault(result.payment_request_id, []).append(
                ApprovalEntry(approver_id=approver_id, approve=approve, at=datetime.now(UTC)))
        self.approval_results[result.payment_request_id] = result

    def mark_paid(self, request_id: int) -> PaymentRecord:
        """PAID_SIMULATED, and one more payment to that bank account."""
        self.set_request_status(request_id, InvoiceStatus.PAID_SIMULATED)
        request = self.payment_requests[request_id]
        self.paid_counts[request.bank_account_id] = self.times_paid(request.bank_account_id) + 1
        return request

    def set_account_status(self, account_id: int, status: BankAccountStatus) -> None:
        self.bank_accounts[account_id] = self.bank_accounts[account_id].model_copy(update={"status": status})


def _sample_sha(name) -> str:
    """Stand-in file hash for the sample invoices (there are no real files behind them)."""
    return hashlib.sha256(f"sample-invoice-{name}".encode()).hexdigest()


def seeded_store() -> Store:
    s = Store()
    created = _at("2026-10-01T09:00:00")

    for cid, name in [(DELTA, "Delta Trading Co."), (OTHER, "Other Test Co.")]:
        s.companies[cid] = Company(id=cid, name=name, created_at=created)

    for uid, company, key, name, role in [
        (KARIM, DELTA, "karim", "Karim Ashraf", Role.ADMIN),
        (MONA, DELTA, "mona", "Mona", Role.APPROVER),
        (SARA, DELTA, "sara", "Sara", Role.ACCOUNTANT),
        (OMAR, DELTA, "omar", "Omar", Role.ACCOUNTANT),
        (VIEWER, DELTA, "viewer", "Viewer", Role.VIEWER),
        (OUTSIDER, OTHER, "outsider", "Outside User", Role.ADMIN),
    ]:
        s.users[uid] = User(id=uid, company_id=company, email=f"{key}@example.com",
                            full_name=name, role=role, created_at=created)

    for vid, name in [(NILE, "Nile Paper"), (EGPACK, "Egyptian Packaging"),
                      (CAIRONET, "Cairo Net"), (AMAL, "Al Amal Transport")]:
        s.vendors[vid] = Vendor(id=vid, company_id=DELTA, name=name, created_at=created)

    # Fake IBANs with valid check digits.
    def add_account(aid: int, vendor: int, bank: str, iban: str, status: BankAccountStatus,
                    paid: int, hold_until: datetime | None = None) -> None:
        s.bank_accounts[aid] = BankAccount(id=aid, company_id=DELTA, vendor_id=vendor, bank_name=bank,
                                           iban=iban, status=status, hold_until=hold_until, created_at=created)
        s.paid_counts[aid] = paid

    add_account(ACC_NILE, NILE, "NBE", "EG380019000500000000263180002", BankAccountStatus.VERIFIED, 9)
    add_account(ACC_EGPACK_OLD, EGPACK, "NBE", "EG430019000500000000263180009", BankAccountStatus.VERIFIED, 14)
    add_account(ACC_EGPACK_NEW, EGPACK, "BM", "EG670037012400000000017907115", BankAccountStatus.ON_HOLD, 0,
                hold_until=_at("2026-11-04T19:15:00"))
    add_account(ACC_CAIRONET, CAIRONET, "CIB", "EG030010000000000100012345678", BankAccountStatus.VERIFIED, 22)
    add_account(ACC_AMAL, AMAL, "NBE", "EG450019000500000000099112233", BankAccountStatus.VERIFIED, 5)
    s.bank_change_requested_by[EGPACK] = OMAR

    # Every invoice a sample record points to exists, so the same data loads into PostgreSQL
    # with its foreign keys: 371 is the earlier, paid invoice that 412 duplicates.
    s.invoices[INV_0371] = Invoice(
        id=INV_0371, company_id=DELTA, vendor_id=NILE, source=InvoiceSource.UPLOAD,
        status=InvoiceStatus.PAID_SIMULATED, file_key="invoices/sample/0371.pdf", file_sha256=_sample_sha("0371"), category="materials",
        uploaded_by=SARA, created_at=_at("2026-10-12T09:00:00"),
    )
    for inv_id, vendor in [(415, EGPACK), (416, CAIRONET), (417, AMAL)]:
        s.invoices[inv_id] = Invoice(
            id=inv_id, company_id=DELTA, vendor_id=vendor, source=InvoiceSource.UPLOAD,
            status=InvoiceStatus.VALIDATED, file_key=f"invoices/sample/0{inv_id}.pdf", file_sha256=_sample_sha(inv_id),
            uploaded_by=SARA, created_at=_at("2026-11-02T09:00:00"),
        )
    s.invoices[INV_0412] = Invoice(
        id=INV_0412, company_id=DELTA, vendor_id=NILE, source=InvoiceSource.UPLOAD, status=InvoiceStatus.FLAGGED,
        file_key="invoices/sample/0412.pdf", file_sha256=_sample_sha("0412"), duplicate_of=INV_0371,
        category="materials",
        uploaded_by=SARA, created_at=_at("2026-11-02T09:10:00"),
        fields=InvoiceData(
            vendor="Nile Paper", invoice_no="INV-2026-0412", date="2026-10-28", amount=Decimal("15400.00"),
            iban="EG380019000500000000263180002",
            field_confidence={"vendor": 0.98, "invoice_no": 0.97, "date": 0.95, "amount": 0.93, "iban": 0.72},
        ),
    )

    # Dated relative to start-up: the gateway voids approvals on a request older than its expiry
    # window (72 h by default), so fixed dates would make every sample request expired.
    now = datetime.now(UTC).replace(microsecond=0)

    def add_request(rid: int, vendor: int, account: int, invoice: int, amount: str, by: int, hours_ago: int) -> None:
        s.payment_requests[rid] = PaymentRecord(
            id=rid, company_id=DELTA, vendor_id=vendor, bank_account_id=account, invoice_id=invoice,
            amount=Decimal(amount), currency="EGP", status=InvoiceStatus.PENDING_APPROVAL,
            creator_id=by, created_at=now - timedelta(hours=hours_ago),
        )

    add_request(PR_187, NILE, ACC_NILE, INV_0412, "15400.00", SARA, hours_ago=6)
    add_request(PR_188, EGPACK, ACC_EGPACK_OLD, 415, "8750.00", SARA, hours_ago=5)
    add_request(PR_189, CAIRONET, ACC_CAIRONET, 416, "2300.00", OMAR, hours_ago=3)
    add_request(PR_190, AMAL, ACC_AMAL, 417, "12000.00", KARIM, hours_ago=2)

    s.risks[PR_187] = RiskScore(
        score=72, level=RiskLevel.HIGH, model_version="rules-0.1",
        rule_hits=["DUPLICATE_INVOICE", "AMOUNT_ABOVE_VENDOR_AVERAGE", "FIRST_PAYMENT_THIS_QUARTER"],
        shap_reasons=[
            ShapReason(feature="DUPLICATE_INVOICE", value=1, contribution=45),
            ShapReason(feature="AMOUNT_ABOVE_VENDOR_AVERAGE", value=2.3, contribution=20),
            ShapReason(feature="FIRST_PAYMENT_THIS_QUARTER", value=1, contribution=7),
        ],
    )
    s.risks[PR_188] = RiskScore(score=41, level=RiskLevel.MEDIUM, model_version="rules-0.1")
    s.risks[PR_189] = RiskScore(score=8, level=RiskLevel.LOW, model_version="rules-0.1")
    s.risks[PR_190] = RiskScore(score=12, level=RiskLevel.LOW, model_version="rules-0.1")
    return s
