# contracts

Shared Pydantic models (`securefin_contracts`) used by every service. Change them only in a separate pull request approved by every affected owner.

Add fields with a default; never rename or remove one.

| File | Models |
|---|---|
| `common.py` | `Role`, `Decision`, `RiskLevel`, `InvoiceStatus`, `Contract` base, `Money` (Decimal, never float), `EgyptianIBAN` (checked), `Language`, `Currency` |
| `companies.py` | `Company`, `User` |
| `vendors.py` | `Vendor`, `BankAccount`, `BankAccountChangeRequest` |
| `invoice.py` | `InvoiceData` (the extractor's only output), `Invoice` (stored record) |
| `payments.py` | `PaymentRequestCreate`, `PaymentRequest` |
| `actions.py` | `ProposedAction`, `ChatRequest`, `ChatResponse` |
| `gateway.py` | `AuthorizeRequest`, `GatewayDecision`, `ApprovalRequest`, `ApprovalRecord`, `ApprovalPayload` (what gets signed) |
| `risk.py` | `RiskRequest`, `RiskScore` |
| `audit.py` | `AuditEvent`, `AuditEntry` |
