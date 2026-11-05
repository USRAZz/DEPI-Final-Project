"""In-memory data store with sample data.

Stands in for PostgreSQL until the real tables land. Routes only use the methods
here, so swapping in a database-backed store changes this file only. Every lookup
takes the caller's company_id: a record from another company is "not found", never
"forbidden", so its existence does not leak.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import TypeVar

from securefin_contracts import (
    BankAccount,
    BankAccountStatus,
    Company,
    Invoice,
    InvoiceData,
    InvoiceSource,
    InvoiceStatus,
    Money,
    PaymentRequest,
    PaymentRequestStatus,
    RiskLevel,
    RiskScore,
    Role,
    ShapReason,
    User,
    Vendor,
)

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


@dataclass
class Store:
    companies: dict[int, Company] = field(default_factory=dict)
    users: dict[int, User] = field(default_factory=dict)
    vendors: dict[int, Vendor] = field(default_factory=dict)
    bank_accounts: dict[int, BankAccount] = field(default_factory=dict)
    times_paid: dict[int, int] = field(default_factory=dict)
    invoices: dict[int, Invoice] = field(default_factory=dict)
    payment_requests: dict[int, PaymentRequest] = field(default_factory=dict)
    risk: dict[int, RiskScore] = field(default_factory=dict)
    bank_change_requested_by: dict[int, int] = field(default_factory=dict)

    # -- reads, always scoped to one company ---------------------------------

    def user(self, user_id: int) -> User | None:
        return self.users.get(user_id)

    def _scoped(self, table: dict[int, T], item_id: int, company_id: int) -> T | None:
        item = table.get(item_id)
        return item if item is not None and item.company_id == company_id else None

    def vendor(self, vendor_id: int, company_id: int) -> Vendor | None:
        return self._scoped(self.vendors, vendor_id, company_id)

    def invoice(self, invoice_id: int, company_id: int) -> Invoice | None:
        return self._scoped(self.invoices, invoice_id, company_id)

    def payment_request(self, request_id: int, company_id: int) -> PaymentRequest | None:
        return self._scoped(self.payment_requests, request_id, company_id)

    def bank_account(self, account_id: int, company_id: int) -> BankAccount | None:
        return self._scoped(self.bank_accounts, account_id, company_id)

    def vendor_accounts(self, vendor_id: int, company_id: int) -> list[BankAccount]:
        return [a for a in self.bank_accounts.values() if a.vendor_id == vendor_id and a.company_id == company_id]

    def pending_requests(self, company_id: int) -> list[PaymentRequest]:
        return sorted(
            (p for p in self.payment_requests.values()
             if p.company_id == company_id and p.status == PaymentRequestStatus.PENDING_APPROVAL),
            key=lambda p: p.created_at,
        )

    def flagged_invoice_count(self, company_id: int) -> int:
        return sum(1 for i in self.invoices.values() if i.company_id == company_id and i.status == InvoiceStatus.FLAGGED)

    def on_hold_account_count(self, company_id: int) -> int:
        return sum(1 for a in self.bank_accounts.values()
                   if a.company_id == company_id and a.status == BankAccountStatus.ON_HOLD)

    def set_request_status(self, request_id: int, status: PaymentRequestStatus) -> None:
        self.payment_requests[request_id] = self.payment_requests[request_id].model_copy(update={"status": status})


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
        s.times_paid[aid] = paid

    add_account(ACC_NILE, NILE, "NBE", "EG380019000500000000263180002", BankAccountStatus.VERIFIED, 9)
    add_account(ACC_EGPACK_OLD, EGPACK, "NBE", "EG430019000500000000263180009", BankAccountStatus.VERIFIED, 14)
    add_account(ACC_EGPACK_NEW, EGPACK, "BM", "EG670037012400000000017907115", BankAccountStatus.ON_HOLD, 0,
                hold_until=_at("2026-11-04T19:15:00"))
    add_account(ACC_CAIRONET, CAIRONET, "CIB", "EG030010000000000100012345678", BankAccountStatus.VERIFIED, 22)
    add_account(ACC_AMAL, AMAL, "NBE", "EG450019000500000000099112233", BankAccountStatus.VERIFIED, 5)
    s.bank_change_requested_by[EGPACK] = OMAR

    s.invoices[INV_0412] = Invoice(
        id=INV_0412, company_id=DELTA, vendor_id=NILE, source=InvoiceSource.UPLOAD, status=InvoiceStatus.FLAGGED,
        file_key="invoices/sample/0412.pdf", duplicate_of=INV_0371, category="materials",
        uploaded_by=SARA, created_at=_at("2026-11-02T09:10:00"),
        fields=InvoiceData(
            vendor="Nile Paper", invoice_no="INV-2026-0412", date="2026-10-28", amount=Decimal("15400.00"),
            iban="EG380019000500000000263180002",
            field_confidence={"vendor": 0.98, "invoice_no": 0.97, "date": 0.95, "amount": 0.93, "iban": 0.72},
        ),
    )

    def add_request(rid: int, vendor: int, account: int, invoice: int, amount: str, by: int, at: str) -> None:
        s.payment_requests[rid] = PaymentRequest(
            id=rid, company_id=DELTA, vendor_id=vendor, bank_account_id=account, invoice_ids=[invoice],
            money=Money(amount=Decimal(amount)), status=PaymentRequestStatus.PENDING_APPROVAL,
            created_by=by, created_at=_at(at),
        )

    add_request(PR_187, NILE, ACC_NILE, INV_0412, "15400.00", SARA, "2026-11-02T10:00:00")
    add_request(PR_188, EGPACK, ACC_EGPACK_OLD, 415, "8750.00", SARA, "2026-11-02T11:30:00")
    add_request(PR_189, CAIRONET, ACC_CAIRONET, 416, "2300.00", OMAR, "2026-11-03T08:05:00")
    add_request(PR_190, AMAL, ACC_AMAL, 417, "12000.00", KARIM, "2026-11-03T08:40:00")

    s.risk[PR_187] = RiskScore(
        score=72, level=RiskLevel.HIGH, model_version="rules-0.1",
        rule_hits=["DUPLICATE_INVOICE", "AMOUNT_ABOVE_VENDOR_AVERAGE", "FIRST_PAYMENT_THIS_QUARTER"],
        shap_reasons=[
            ShapReason(feature="DUPLICATE_INVOICE", value=1, contribution=45),
            ShapReason(feature="AMOUNT_ABOVE_VENDOR_AVERAGE", value=2.3, contribution=20),
            ShapReason(feature="FIRST_PAYMENT_THIS_QUARTER", value=1, contribution=7),
        ],
    )
    s.risk[PR_188] = RiskScore(score=41, level=RiskLevel.MEDIUM, model_version="rules-0.1")
    s.risk[PR_189] = RiskScore(score=8, level=RiskLevel.LOW, model_version="rules-0.1")
    s.risk[PR_190] = RiskScore(score=12, level=RiskLevel.LOW, model_version="rules-0.1")
    return s
