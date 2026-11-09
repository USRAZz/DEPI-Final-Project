# Week 2 draft: invoice extraction contract

Status: proposal for the contract-change PR. This file does not change the current Pydantic models.

## Why a change is needed

`InvoiceData` currently has one ambiguous `amount`, does not represent tax or purchase-order data, omits tax registration numbers, and has no `line_total` on each line. The synthetic fixtures now include multiple line items and a computed subtotal, VAT, and total. The shared contract should represent those values explicitly before the extractor and API build against different assumptions.

## Proposed canonical fields

| Field | Proposed shape | Notes |
|---|---|---|
| `vendor_name` | string, up to 200 chars | Text observed on invoice; vendor registry matching happens outside the extractor. |
| `invoice_number` | string, up to 64 chars | Preserve the printed value. |
| `invoice_date` | ISO date | Normalize supported Arabic/English date formats. |
| `purchase_order` | nullable string | Optional on source invoices. |
| `tax_id` | nullable string | Supplier registration number as printed. |
| `currency` | ISO-4217-style three-letter string | Default EGP only when the document explicitly indicates EGP or policy permits the default. |
| `line_items` | list of line items | Empty/partial extraction must be distinguishable from a verified zero-line invoice. |
| `subtotal` | decimal amount | Amount before tax. |
| `tax_rate` | nullable decimal | For example, `0.14`; do not infer if not printed. |
| `tax_amount` | nullable decimal amount | VAT/tax amount as printed. |
| `total` | decimal amount | Invoice total due. Replaces the ambiguous `amount` after migration. |
| `iban_observed` | nullable bounded string | Untrusted text from the invoice. It must never be used as the payment destination. |
| `field_confidence` | map of field name to number in `[0, 1]` | Confidence is a review signal, not authorization. |

Each line item should contain `description`, positive `quantity`, non-negative `unit_price`, and nullable `line_total`. Use `Decimal` for all monetary values and preserve the currency separately.

## Validation and safety rules

1. Keep `extra="forbid"`; unexpected model output becomes `NEEDS_REVIEW`.
2. Missing or unreadable required values become an explicit review result; do not fabricate defaults.
3. Check arithmetic with a small currency rounding tolerance: line totals vs subtotal, then subtotal + tax vs total. A mismatch means review, not silent correction.
4. Do not reject a low-quality OCR result solely because the observed account string fails IBAN validation. Preserve it as untrusted evidence and route the invoice for review; only a verified vendor record may supply a payment destination.
5. Raw OCR text remains inside the extractor boundary. Only schema-validated fields and confidence leave that service; raw text is not sent to the Finance Agent.
6. Names in the first two sets are bilingual; preserve the script in `vendor_name` and do not normalize Arabic spelling in stored data. Apply search normalization separately.

## Required review before implementation

- Extractor owner: required vs nullable fields and confidence behavior.
- API/database owner: field names and decimal precision.
- Gateway/security owner: review behavior for low confidence, mismatched totals, and invoice IBAN.
- UI owner: how missing fields and review reasons are shown in Arabic and English.

After agreement, copy the accepted schema into `invoice.py` through a dedicated contract-change PR and update all consumers together.
