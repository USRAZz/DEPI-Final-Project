"""Initial schema: tenants, users, vendors, invoices, payment requests, approvals, audit, with row-level security.

Decisions (week 2, defaults taken 2026-11-10; see deferred/SCHEMA_PROPOSAL.md):
- Integer ids (BIGINT identity), matching the shared contracts (invoice_id, vendor_id are int).
- Row-level security is ON from the first migration. Every tenant table is filtered by the transaction
  setting app.company_id. No setting -> zero rows.
- The exact same file cannot be stored twice per company: UNIQUE (company_id, source_hash).
  The same (vendor, invoice number) is only indexed: a repeat is a duplicate signal for review, not a reject.
- File bytes live on a Docker volume; the row stores object key, sha256, MIME type, size and upload time.
- Status columns use the shared InvoiceStatus values (contracts/securefin_contracts/common.py).

How the services must connect (PostgreSQL superusers and table owners skip RLS):
    BEGIN;
    SET LOCAL ROLE securefin_app;        -- the api; the gateway uses securefin_gateway
    SELECT set_config('app.company_id', '<company id from the session>', true);
    ... queries ...
    COMMIT;
Write ownership (GitHub issue #15): approvals and audit_log belong to the gateway. securefin_gateway may only
SELECT and INSERT them (append-only, no UPDATE/DELETE). securefin_app (the api) has no access to them at all,
so the api cannot forge an approval or edit history; it reads them through gateway endpoints.

Revision ID: 0001
Revises:
Create Date: 2026-11-10
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLE = "securefin_app"          # api
GATEWAY_ROLE = "securefin_gateway"  # gateway: the only writer of approvals and audit_log
INVOICE_STATUSES = ("VALIDATED", "NEEDS-REVIEW", "FLAGGED", "VENDOR_CHANGE_PENDING",
                    "PENDING_APPROVAL", "PAID_SIMULATED", "REJECTED")
ROLES = ("viewer", "accountant", "approver", "admin")
API_TABLES = ("users", "vendors", "invoices", "invoice_line_items", "payment_requests")
GATEWAY_TABLES = ("approvals", "audit_log")


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


TENANT = "NULLIF(current_setting('app.company_id', true), '')::bigint"

SCHEMA = f"""
CREATE TABLE companies (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id    BIGINT NOT NULL REFERENCES companies(id),
    email         TEXT NOT NULL CHECK (email = lower(email) AND position('@' IN email) > 1),
    display_name  TEXT NOT NULL DEFAULT '',
    role          TEXT NOT NULL CHECK (role IN ({_in(ROLES)})),
    is_active     BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, email),
    UNIQUE (company_id, id)
);

CREATE TABLE vendors (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id     BIGINT NOT NULL REFERENCES companies(id),
    name           TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
    tax_id         TEXT,
    -- The only payment destination. Changed through the gateway bank-change workflow, never from an invoice.
    verified_iban  TEXT CHECK (verified_iban ~ '^[A-Z]{{2}}[0-9]{{2}}[A-Z0-9]{{10,30}}$'),
    iban_status    TEXT NOT NULL DEFAULT 'unverified'
                   CHECK (iban_status IN ('unverified', 'verified', 'change_pending')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, id)
);

CREATE TABLE invoices (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id       BIGINT NOT NULL REFERENCES companies(id),
    vendor_id        BIGINT,  -- NULL until the extracted vendor is matched to the registry
    invoice_number   TEXT CHECK (length(invoice_number) <= 64),
    invoice_date     DATE,
    purchase_order   TEXT,
    tax_id_observed  TEXT,
    -- Untrusted text read from the document. Never a payment destination.
    iban_observed    TEXT CHECK (length(iban_observed) <= 34),
    currency         CHAR(3) NOT NULL DEFAULT 'EGP' CHECK (currency ~ '^[A-Z]{{3}}$'),
    subtotal         NUMERIC(14, 2) CHECK (subtotal >= 0),
    tax_rate         NUMERIC(5, 4) CHECK (tax_rate >= 0 AND tax_rate < 1),
    tax_amount       NUMERIC(14, 2) CHECK (tax_amount >= 0),
    total            NUMERIC(14, 2) CHECK (total >= 0),
    status           TEXT NOT NULL DEFAULT 'NEEDS-REVIEW' CHECK (status IN ({_in(INVOICE_STATUSES)})),
    issue_codes      TEXT[] NOT NULL DEFAULT '{{}}',
    ocr_confidence   NUMERIC(4, 3) CHECK (ocr_confidence BETWEEN 0 AND 1),
    category         TEXT CHECK (length(category) <= 64),
    source_key       TEXT NOT NULL,  -- generated object key on the files volume, never the client's file name
    source_hash      CHAR(64) NOT NULL CHECK (source_hash ~ '^[0-9a-f]{{64}}$'),  -- sha256 of the bytes
    source_mime      TEXT NOT NULL,
    source_size      BIGINT NOT NULL CHECK (source_size > 0),
    uploaded_by      BIGINT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, id),
    UNIQUE (company_id, source_hash),
    FOREIGN KEY (company_id, vendor_id) REFERENCES vendors (company_id, id),
    FOREIGN KEY (company_id, uploaded_by) REFERENCES users (company_id, id)
);
-- Duplicate signal (same vendor + number), deliberately not unique.
CREATE INDEX invoices_vendor_number_idx ON invoices (company_id, vendor_id, invoice_number);
CREATE INDEX invoices_status_idx ON invoices (company_id, status);

CREATE TABLE invoice_line_items (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id   BIGINT NOT NULL,
    invoice_id   BIGINT NOT NULL,
    position     INTEGER NOT NULL CHECK (position >= 1),
    description  TEXT NOT NULL CHECK (length(description) <= 300),
    quantity     NUMERIC(14, 4) NOT NULL CHECK (quantity > 0),
    unit_price   NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),
    line_total   NUMERIC(14, 2) CHECK (line_total >= 0),
    UNIQUE (invoice_id, position),
    FOREIGN KEY (company_id, invoice_id) REFERENCES invoices (company_id, id) ON DELETE CASCADE
);

CREATE TABLE payment_requests (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id    BIGINT NOT NULL,
    invoice_id    BIGINT NOT NULL,
    vendor_id     BIGINT NOT NULL,
    created_by    BIGINT NOT NULL,
    amount        NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    currency      CHAR(3) NOT NULL DEFAULT 'EGP' CHECK (currency ~ '^[A-Z]{{3}}$'),
    status        TEXT NOT NULL DEFAULT 'PENDING_APPROVAL' CHECK (status IN ({_in(INVOICE_STATUSES)})),
    risk_score    NUMERIC(5, 2) CHECK (risk_score BETWEEN 0 AND 100),
    request_hash  CHAR(64) NOT NULL,  -- idempotency: the same proposal is stored once
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, id),
    UNIQUE (company_id, request_hash),
    FOREIGN KEY (company_id, invoice_id) REFERENCES invoices (company_id, id),
    FOREIGN KEY (company_id, vendor_id) REFERENCES vendors (company_id, id),
    FOREIGN KEY (company_id, created_by) REFERENCES users (company_id, id)
);
CREATE INDEX payment_requests_invoice_idx ON payment_requests (company_id, invoice_id);

CREATE TABLE approvals (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id          BIGINT NOT NULL,
    payment_request_id  BIGINT NOT NULL,
    approver_id         BIGINT NOT NULL,
    approve             BOOLEAN NOT NULL,
    comment             TEXT NOT NULL DEFAULT '' CHECK (length(comment) <= 500),
    hmac_signature      TEXT NOT NULL,
    signed_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- An approval older than this is EXPIRED and not counted (gateway approval_expiry_hours = 72).
    expires_at          TIMESTAMPTZ NOT NULL DEFAULT now() + interval '72 hours',
    CHECK (expires_at > signed_at),
    UNIQUE (payment_request_id, approver_id),  -- one person cannot approve twice
    FOREIGN KEY (company_id, payment_request_id) REFERENCES payment_requests (company_id, id),
    FOREIGN KEY (company_id, approver_id) REFERENCES users (company_id, id)
);

-- Columns follow contracts/securefin_contracts/audit.py AuditEntry, plus company_id (GitHub issue #15).
-- Hash chain: entry_hash[n] = SHA256(entry_data[n] + entry_hash[n-1]); the first prev_hash is '0' * 64.
CREATE TABLE audit_log (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
    company_id      BIGINT NOT NULL REFERENCES companies(id),
    user_id         BIGINT,
    action          TEXT NOT NULL CHECK (length(action) <= 100),
    tool_call       TEXT,
    parameters      JSONB NOT NULL DEFAULT '{{}}'::jsonb,  -- already masked by the caller
    decision        TEXT,
    risk_level      TEXT,
    result          TEXT,
    source_service  TEXT NOT NULL,
    prev_hash       CHAR(64) NOT NULL CHECK (prev_hash ~ '^[0-9a-f]{{64}}$'),
    entry_hash      CHAR(64) NOT NULL UNIQUE CHECK (entry_hash ~ '^[0-9a-f]{{64}}$'),
    FOREIGN KEY (company_id, user_id) REFERENCES users (company_id, id)
);
CREATE INDEX audit_log_company_idx ON audit_log (company_id, id);
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    for role in (APP_ROLE, GATEWAY_ROLE):
        op.execute(f"""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                    CREATE ROLE {role} NOLOGIN;
                END IF;
            END $$;
        """)
    op.execute(f"ALTER TABLE companies ENABLE ROW LEVEL SECURITY; ALTER TABLE companies FORCE ROW LEVEL SECURITY;"
               f"CREATE POLICY tenant_isolation ON companies USING (id = {TENANT}) WITH CHECK (id = {TENANT});"
               f"GRANT SELECT ON companies TO {APP_ROLE};")
    for t in API_TABLES + GATEWAY_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY; ALTER TABLE {t} FORCE ROW LEVEL SECURITY;"
                   f"CREATE POLICY tenant_isolation ON {t} "
                   f"USING (company_id = {TENANT}) WITH CHECK (company_id = {TENANT});")
    for t in API_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO {APP_ROLE};")
    for t in GATEWAY_TABLES:  # append-only, and only for the gateway
        op.execute(f"GRANT SELECT, INSERT ON {t} TO {GATEWAY_ROLE};")


def downgrade() -> None:
    for t in GATEWAY_TABLES[::-1] + API_TABLES[::-1] + ("companies",):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE;")
    for role in (APP_ROLE, GATEWAY_ROLE):
        op.execute(f"DROP ROLE IF EXISTS {role};")
