from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from securefin_contracts import (
    AuthorizeRequest,
    BankAccount,
    BankAccountStatus,
    Decision,
    GatewayDecision,
    Invoice,
    Money,
    PaymentRequest,
    PaymentRequestStatus,
    ProposedAction,
    Role,
    User,
)

from .clients import gateway_authorize
from .deps import GatewayDep, StoreDep, UserDep
from .gateway import DUAL_APPROVAL_LIMIT, ApprovalRefused, Gateway
from .schemas import (
    AccountView,
    ApprovalIn,
    ApprovalView,
    BankChangeView,
    DashboardView,
    PaymentRequestView,
    PendingRow,
)
from .store import Store

router = APIRouter()

APPROVER_ROLES = {Role.ADMIN, Role.APPROVER}

# Sample figure until paid payments are stored.
MONTH_SPEND = Money(amount=Decimal("486250.00"))
INVOICES_PAID = 38


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def _account_view(store: Store, account: BankAccount) -> AccountView:
    return AccountView(**account.model_dump(), times_paid=store.times_paid.get(account.id, 0))


def _decide(gateway: Gateway, request: PaymentRequest, store: Store) -> GatewayDecision:
    """Ask the gateway. Any failure is a BLOCK: no decision means no payment."""
    try:
        return gateway.decide(request, store.risk.get(request.id))
    except Exception:
        return GatewayDecision(decision=Decision.BLOCK, reasons=["GATEWAY_UNAVAILABLE"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "api", "status": "ok"}


@router.post("/payments/propose")
async def propose_payment(action: ProposedAction):
    """Skeleton path: agent proposal -> gateway decision -> execute only on ALLOW. (Auth is stubbed.)"""
    req = AuthorizeRequest(user_id=1, role=Role.ACCOUNTANT, company_id=1, action=action, request_id="demo-1")
    decision = await gateway_authorize(req)
    executed = decision.decision == Decision.ALLOW  # TODO(Karim): real simulated executor + HMAC re-check
    return {"decision": decision.model_dump(), "executed": executed}


@router.get("/me")
def me(user: UserDep) -> User:
    return user


@router.get("/dashboard")
def dashboard(user: UserDep, store: StoreDep) -> DashboardView:
    pending = store.pending_requests(user.company_id)
    return DashboardView(
        month_spend=MONTH_SPEND,
        invoices_paid=INVOICES_PAID,
        pending_count=len(pending),
        above_limit_count=sum(p.money.amount > DUAL_APPROVAL_LIMIT for p in pending),
        flagged_count=store.flagged_invoice_count(user.company_id),
        on_hold_count=store.on_hold_account_count(user.company_id),
        pending=[
            PendingRow(
                request=p,
                vendor=store.vendors[p.vendor_id],
                created_by=store.users[p.created_by],
                risk=store.risk.get(p.id),
            )
            for p in pending
        ],
    )


@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int, user: UserDep, store: StoreDep) -> Invoice:
    invoice = store.invoice(invoice_id, user.company_id)
    if invoice is None:
        raise _not_found("invoice")
    return invoice


def _payment_view(request: PaymentRequest, store: Store, gateway: Gateway) -> PaymentRequestView:
    account = store.bank_account(request.bank_account_id, request.company_id)
    if account is None:
        raise _not_found("bank account")
    return PaymentRequestView(
        request=request,
        vendor=store.vendors[request.vendor_id],
        account=_account_view(store, account),
        created_by=store.users[request.created_by],
        risk=store.risk.get(request.id),
        gateway=_decide(gateway, request, store),
        approvals=[
            ApprovalView(approver=store.users[r.approver_id], approved=r.approve, signed_at=r.signed_at)
            for r in gateway.approvals(request.id)
        ],
    )


@router.get("/payment-requests/{request_id}")
def get_payment_request(request_id: int, user: UserDep, store: StoreDep, gateway: GatewayDep) -> PaymentRequestView:
    request = store.payment_request(request_id, user.company_id)
    if request is None:
        raise _not_found("payment request")
    return _payment_view(request, store, gateway)


@router.post("/payment-requests/{request_id}/approvals", status_code=status.HTTP_201_CREATED)
def decide_payment_request(
    request_id: int, body: ApprovalIn, user: UserDep, store: StoreDep, gateway: GatewayDep
) -> PaymentRequestView:
    request = store.payment_request(request_id, user.company_id)
    if request is None:
        raise _not_found("payment request")
    if user.role not in APPROVER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "your role cannot approve payments")
    if request.status != PaymentRequestStatus.PENDING_APPROVAL:
        raise HTTPException(status.HTTP_409_CONFLICT, "request is not awaiting approval")
    # The bank account must still be verified: an approval signs this exact account.
    account = store.bank_account(request.bank_account_id, user.company_id)
    if account is None or account.status != BankAccountStatus.VERIFIED:
        raise HTTPException(status.HTTP_409_CONFLICT, "bank account is not verified")

    try:
        gateway.record(request, account, user, body.approved)
    except ApprovalRefused as refused:
        code = status.HTTP_403_FORBIDDEN if refused.code == "SELF_APPROVAL" else status.HTTP_409_CONFLICT
        raise HTTPException(code, refused.code) from None
    except Exception:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "gateway unavailable; nothing was recorded") from None

    decision = _decide(gateway, request, store)
    if decision.decision == Decision.ALLOW:
        store.set_request_status(request.id, PaymentRequestStatus.APPROVED)
    elif "REJECTED_BY_APPROVER" in decision.reasons:
        store.set_request_status(request.id, PaymentRequestStatus.REJECTED)
    return _payment_view(store.payment_requests[request.id], store, gateway)


@router.get("/vendors/{vendor_id}/bank-change")
def bank_change(vendor_id: int, user: UserDep, store: StoreDep) -> BankChangeView:
    vendor = store.vendor(vendor_id, user.company_id)
    if vendor is None:
        raise _not_found("vendor")
    accounts = store.vendor_accounts(vendor_id, user.company_id)
    current = next((a for a in accounts if a.status == BankAccountStatus.VERIFIED), None)
    proposed = next((a for a in accounts if a.status == BankAccountStatus.ON_HOLD), None)
    requested_by = store.bank_change_requested_by.get(vendor_id)
    return BankChangeView(
        vendor=vendor,
        current=_account_view(store, current) if current else None,
        proposed=_account_view(store, proposed) if proposed else None,
        requested_by=store.users.get(requested_by) if requested_by else None,
    )
