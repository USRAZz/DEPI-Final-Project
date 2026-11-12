"""Risk features: facts about one invoice for services/risk (GET /v1/invoices/{id}/risk-features).

The api owns invoices and vendors, so it computes these facts here and sends only booleans and
numbers. Raw bank details (IBANs) never leave the api. The risk service turns the facts into a
score; the gateway decides.

Service-to-service call: there is no user session, so the caller must send the shared
INTERNAL_SERVICE_TOKEN in X-Service-Token. A missing or empty server token rejects every call.
"""

import hmac
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from securefin_contracts import BankAccountStatus, Invoice
from securefin_contracts.risk import RiskFeatures

from .deps import StoreDep
from .store import Store

TOTAL_MISMATCH = "TOTAL_MISMATCH"  # extractor issue code: subtotal + tax != total


def _normalize_iban(value: str) -> str:
    return value.replace(" ", "").upper()


def compute_risk_features(store: Store, invoice: Invoice) -> RiskFeatures:
    """None means "not known", which the risk service scores the same as False."""
    fields = invoice.fields
    accounts = store.vendor_accounts(invoice.vendor_id, invoice.company_id) if invoice.vendor_id else []
    verified = [a for a in accounts if a.status == BankAccountStatus.VERIFIED]

    bank_mismatch: bool | None = None
    if fields is not None and fields.iban and verified:
        observed = _normalize_iban(fields.iban)
        bank_mismatch = all(_normalize_iban(a.iban) != observed for a in verified)

    confidence = invoice.ocr_confidence
    if confidence is None and fields is not None and fields.field_confidence:
        confidence = min(fields.field_confidence.values())

    return RiskFeatures(
        duplicate_detected=invoice.duplicate_of is not None,
        invoice_total_mismatch=TOTAL_MISMATCH in invoice.extraction_issues if invoice.fields else None,
        ocr_confidence=confidence,
        invoice_total_egp=fields.amount if fields is not None and fields.currency == "EGP" else None,
        bank_account_mismatch=bank_mismatch,
        vendor_change_pending=any(a.status == BankAccountStatus.ON_HOLD for a in accounts) if invoice.vendor_id else None,
    )


def require_service_token(x_service_token: Annotated[str | None, Header()] = None) -> None:
    expected = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
    if not expected or not x_service_token or not hmac.compare_digest(x_service_token, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "service token required")


internal_router = APIRouter(prefix="/v1", dependencies=[Depends(require_service_token)], include_in_schema=False)


@internal_router.get("/invoices/{invoice_id}/risk-features")
def risk_features(invoice_id: int, store: StoreDep) -> RiskFeatures:
    # Trusted internal caller with no company context: look the invoice up directly.
    invoice = store.invoices.get(invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")
    return compute_risk_features(store, invoice)
