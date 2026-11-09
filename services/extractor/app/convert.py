"""ExtractionResult (pipeline) -> ExtractResponse (shared contract the api receives)."""
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError
from securefin_contracts import ExtractResponse, InvoiceData, InvoiceStatus, LineItem

from .schemas import ExtractionResult, InvoiceFields

_STATUS = {"READY": InvoiceStatus.VALIDATED, "FLAGGED": InvoiceStatus.FLAGGED, "FAILED": InvoiceStatus.NEEDS_REVIEW}


def _dec(v) -> Decimal | None:
    try:
        return None if v is None else Decimal(str(v)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _line_items(f: InvoiceFields) -> list[LineItem]:
    items = []
    for i in f.line_items:
        qty = _dec(i.quantity) if i.quantity and i.quantity > 0 else Decimal("1")
        price = _dec(i.unit_price)
        if price is None and i.total is not None:
            price = _dec(i.total / float(qty))
        if price is None or price < 0:
            continue  # nothing usable on this line
        items.append(LineItem(description=i.description[:300], quantity=qty, unit_price=price))
    return items


def to_invoice_data(f: InvoiceFields) -> InvoiceData:
    """Raises ValidationError (or ValueError) when the fields do not fit the shared contract."""
    if f.invoice_date is None:
        raise ValueError("invoice date missing")
    return InvoiceData(vendor=f.vendor_name[:200], invoice_no=f.invoice_number[:64], date=f.invoice_date,
                       amount=_dec(f.total_amount), currency=(f.currency or "EGP").upper(),
                       iban=f.iban, line_items=_line_items(f))


def to_response(r: ExtractionResult) -> ExtractResponse:
    codes = list(r.issue_codes)
    data = None
    if r.fields is not None:
        try:
            data = to_invoice_data(r.fields)
        except (ValidationError, ValueError):
            codes.append("SCHEMA_INVALID")
    status = _STATUS[r.status] if data is not None or r.status == "FAILED" else InvoiceStatus.NEEDS_REVIEW
    return ExtractResponse(status=status, data=data, issue_codes=codes[:20], ocr_confidence=r.ocr_confidence,
                           category=r.category.category if r.category else None)
