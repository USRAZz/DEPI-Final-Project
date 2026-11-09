# Week 2 draft: database schema and write ownership

Status: design proposal only. No migration has been applied. Agree on the shared invoice contract first, then implement this through Alembic.

## Entity map

```text
companies 1---* users
companies 1---* vendors 1---* invoices 1---* invoice_line_items
invoices  1---* payment_requests 1---* approvals
companies 1---* audit_events
```

## Proposed tables

| Table | Important columns | Single writer |
|---|---|---|
| `companies` | `id`, `name`, `created_at` | API |
| `users` | `id`, `company_id`, `email`, `display_name`, `role`, `is_active` | API |
| `vendors` | `id`, `company_id`, `name`, `tax_id`, `verified_iban`, `iban_status`, timestamps | API; bank-account changes must go through Gateway workflow |
| `invoices` | `id`, `company_id`, `vendor_id`, `invoice_number`, `invoice_date`, `purchase_order`, `tax_id_observed`, `currency`, `subtotal`, `tax_rate`, `tax_amount`, `total`, `status`, `source_hash`, `created_at` | API |
| `invoice_line_items` | `id`, `company_id`, `invoice_id`, `position`, `description`, `quantity`, `unit_price`, `line_total` | API |
| `payment_requests` | `id`, `company_id`, `invoice_id`, `vendor_id`, `created_by`, `amount`, `currency`, `status`, `risk_score`, `request_hash`, timestamps | API; state transition authorized by Gateway |
| `approvals` | `id`, `company_id`, `payment_request_id`, `approver_id`, `decision`, `signed_payload_hash`, `signature`, `signed_at` | Gateway only |
| `audit_events` | `id`, `company_id`, `actor_id`, `action`, masked `payload`, `decision`, `created_at`, `prev_hash`, `entry_hash` | Gateway only |

## Constraints to include in the first migration

- Every tenant-owned table carries `company_id`; foreign keys include tenant identity where practical so cross-company references fail at the database boundary.
- Unique invoice key: `(company_id, vendor_id, invoice_number)`. This is a duplicate signal, not a reason to discard the second document.
- `quantity > 0`; prices and totals are non-negative; payment amount is positive; currency is a three-letter code.
- Use PostgreSQL `NUMERIC`, never floating point, for money and quantities that require fractions.
- Store the verified vendor IBAN separately from `invoices.iban_observed`. The invoice value must not become a payment destination automatically.
- Enable and force row-level security on tenant tables. Set the active company id inside each transaction; missing tenant context must return no rows.
- Keep approval and audit rows append-only to application roles. Hash-chain verification detects edits; it does not replace database permissions or backups.
- Store file bytes outside PostgreSQL; persist a generated object key, content hash, MIME type, size, and upload timestamp. Do not store real invoice files in Git.

## Decisions needed before Alembic code

1. Whether the course MVP uses numeric ids or UUIDs.
2. Required retention and local file-storage strategy for the demo.
3. How `source_hash` and the unique invoice key combine for duplicate detection.
4. Which invoice statuses belong in the shared enum and which are local workflow states.
5. Whether row-level security is included in the first course demo migration or documented as a later security milestone.

Do not let multiple services write the same table. API owns invoice/vendor/payment-request data; Gateway owns approvals and audit events; other services call their API rather than writing directly.
