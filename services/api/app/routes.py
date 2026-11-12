import os
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from securefin_contracts import (
    ApprovalRequest,
    ApprovalStatus,
    AuthorizeRequest,
    BankAccount,
    BankAccountStatus,
    Decision,
    ExecuteCheckRequest,
    Invoice,
    InvoiceStatus,
    Money,
    PaymentRequestInfo,
    ProposedAction,
    Role,
    User,
)

from .clients import gateway_authorize
from .deps import GatewayDep, StoreDep, UserDep
from .gateway import ApprovalRefused, GatewayUnavailable
from .models import PaymentRecord
from .risk_features import require_service_token
from .schemas import (
    AccountView,
    ApprovalIn,
    ApprovalState,
    ApprovalView,
    BankChangeView,
    DashboardView,
    ExecutionView,
    PaymentRequestView,
    PendingRow,
)
from .store import Store

router = APIRouter()

APPROVER_ROLES = {Role.ADMIN, Role.APPROVER}
EXECUTOR_ROLES = {Role.ADMIN, Role.ACCOUNTANT}

# For the screens only (how many approvals to expect); the gateway's policy decides.
DUAL_APPROVAL_LIMIT = Decimal(os.getenv("DUAL_APPROVAL_THRESHOLD_EGP", "10000"))

# Sample figure until paid payments are stored.
MONTH_SPEND = Money(amount=Decimal("486250.00"))
INVOICES_PAID = 38


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def _account_view(store: Store, account: BankAccount) -> AccountView:
    return AccountView(**account.model_dump(), times_paid=store.times_paid.get(account.id, 0))


def _verified_account(store: Store, request: PaymentRecord) -> BankAccount:
    # The account must still be verified: the payment goes to this exact account.
    account = store.bank_account(request.bank_account_id, request.company_id)
    if account is None or account.status != BankAccountStatus.VERIFIED:
        raise HTTPException(status.HTTP_409_CONFLICT, "bank account is not verified")
    return account


def _approval_state(store: Store, request: PaymentRecord) -> ApprovalState:
    result = store.approval_results.get(request.id)
    if result is not None:
        return ApprovalState(status=result.status, approvals_received=result.approvals_received,
                             approvals_required=result.approvals_required, reasons=result.reasons)
    expected = 2 if request.amount > DUAL_APPROVAL_LIMIT or request.currency != "EGP" else 1
    return ApprovalState(status=ApprovalStatus.PENDING_APPROVAL, approvals_received=0, approvals_required=expected)


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "api", "status": "ok"}


@router.post("/payments/propose")
async def propose_payment(action: ProposedAction):
    """Skeleton path: agent proposal -> gateway decision. (Auth is stubbed.)
    A payment request itself is only paid through POST /payment-requests/{id}/execute."""
    req = AuthorizeRequest(user_id=1, role=Role.ACCOUNTANT, company_id=1, action=action, request_id="demo-1")
    decision = await gateway_authorize(req)
    executed = decision.decision == Decision.ALLOW
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
        above_limit_count=sum(p.amount > DUAL_APPROVAL_LIMIT for p in pending),
        flagged_count=store.flagged_invoice_count(user.company_id),
        on_hold_count=store.on_hold_account_count(user.company_id),
        pending=[
            PendingRow(
                request=p,
                vendor=store.vendors[p.vendor_id],
                created_by=store.users[p.creator_id],
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


def _payment_view(request: PaymentRecord, store: Store) -> PaymentRequestView:
    account = store.bank_account(request.bank_account_id, request.company_id)
    if account is None:
        raise _not_found("bank account")
    return PaymentRequestView(
        request=request,
        vendor=store.vendors[request.vendor_id],
        account=_account_view(store, account),
        created_by=store.users[request.creator_id],
        risk=store.risk.get(request.id),
        approval=_approval_state(store, request),
        approvals=[
            ApprovalView(approver=store.users[e.approver_id], approved=e.approve, at=e.at)
            for e in store.approvals.get(request.id, [])
        ],
    )


@router.get("/payments/{request_id}", dependencies=[Depends(require_service_token)], include_in_schema=False)
def get_payment_info(request_id: int, store: StoreDep) -> PaymentRequestInfo:
    """Service-to-service read for the gateway (approvals and execute-check). Needs X-Service-Token."""
    request = store.payment_requests.get(request_id)
    if request is None:
        raise _not_found("payment request")
    return request.info()


@router.get("/payment-requests/{request_id}")
def get_payment_request(request_id: int, user: UserDep, store: StoreDep) -> PaymentRequestView:
    request = store.payment_request(request_id, user.company_id)
    if request is None:
        raise _not_found("payment request")
    return _payment_view(request, store)


@router.post("/payment-requests/{request_id}/approvals", status_code=status.HTTP_201_CREATED)
def decide_payment_request(
    request_id: int, body: ApprovalIn, user: UserDep, store: StoreDep, gateway: GatewayDep
) -> PaymentRequestView:
    request = store.payment_request(request_id, user.company_id)
    if request is None:
        raise _not_found("payment request")
    if user.role not in APPROVER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, ["your role cannot approve payments"])
    if request.status != InvoiceStatus.PENDING_APPROVAL:
        raise HTTPException(status.HTTP_409_CONFLICT, ["request is not awaiting approval"])
    _verified_account(store, request)

    # Role and company come from the session, never from the request body.
    approval = ApprovalRequest(payment_request_id=request.id, approver_id=user.id, approve=body.approved,
                               comment=body.comment, approver_role=user.role, company_id=user.company_id)
    try:
        result = gateway.submit_approval(approval)
    except ApprovalRefused as refused:
        raise HTTPException(refused.status_code, refused.reasons) from None
    except GatewayUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, ["gateway unavailable: nothing was approved"]) from None

    store.record_approval(user.id, body.approved, result)
    # APPROVED keeps PENDING_APPROVAL: execute-check only allows a payment in that status.
    if result.status == ApprovalStatus.REJECTED:
        store.set_request_status(request.id, InvoiceStatus.REJECTED)
    return _payment_view(store.payment_requests[request.id], store)


@router.post("/payment-requests/{request_id}/execute")
def execute_payment_request(request_id: int, user: UserDep, store: StoreDep, gateway: GatewayDep) -> ExecutionView:
    """Simulated payment. Runs only when the gateway's execute-check says allowed, right before paying."""
    request = store.payment_request(request_id, user.company_id)
    if request is None:
        raise _not_found("payment request")
    if user.role not in EXECUTOR_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, ["your role cannot execute payments"])
    if request.status != InvoiceStatus.PENDING_APPROVAL:
        raise HTTPException(status.HTTP_409_CONFLICT, [f"request is {request.status.value}, not awaiting execution"])
    account = _verified_account(store, request)

    check = ExecuteCheckRequest(payment_request_id=request.id, requested_by=user.id, company_id=user.company_id)
    try:
        result = gateway.execute_check(check)
    except ApprovalRefused as refused:
        raise HTTPException(refused.status_code, refused.reasons) from None
    except GatewayUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, ["gateway unavailable: nothing was paid"]) from None
    if not result.allowed:
        raise HTTPException(status.HTTP_409_CONFLICT, result.reasons or ["gateway did not allow execution"])

    store.set_request_status(request.id, InvoiceStatus.PAID_SIMULATED)
    store.times_paid[account.id] = store.times_paid.get(account.id, 0) + 1
    return ExecutionView(request=store.payment_requests[request.id], executed=True)


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
