# SecureFin Gateway: Threat Model

Owner: Anan Alaa. Status: draft v0.1 for review at kickoff.

## Scope
The gateway (`services/gateway`) decides ALLOW, HOLD or BLOCK for every action proposed by a user or by the AI assistant. It also owns approvals, bank-detail changes and the audit log.

## Assets
- Payment requests and their approvals
- Vendor bank details
- The audit log
- Company data (each company must never see another's)

## Actors
- Legitimate users (Viewer, Accountant, Approver, Admin)
- A malicious or careless insider
- An outside attacker who sends a crafted invoice
- A compromised or manipulated AI assistant

## Trust rules
1. The assistant is untrusted. It can only propose.
2. Invoice text is untrusted input.
3. Only the API executes, and only after the gateway returns ALLOW.
4. If the gateway is down or slow, the answer is BLOCK.

## Threats

| ID | Threat | How it happens | Control | Reason code | Test that catches it |
| --- | --- | --- | --- | --- | --- |
| T01 | Self-approval | Creator approves their own payment | Gateway compares creator ID and approver ID | `SELF_APPROVAL` | Unit + attack suite |
| T02 | Approval tampering | Amount or account edited after approval | Signature covers the exact payload; execute re-verifies | `APPROVAL_PAYLOAD_MISMATCH` | Unit + attack suite |
| T03 | Bank-detail swap | Vendor account changed right before payment | Change puts vendor on HOLD (cooling period) and needs confirmation | `BANK_CHANGE_COOLING`, `BANK_CHANGE_UNCONFIRMED` | Unit + attack suite |
| T04 | Hidden instructions in an invoice (prompt injection) | Invoice text tells the assistant to pay or approve | Extractor returns fixed fields only; assistant cannot execute; gateway judges every action | `ACTION_NOT_ALLOWED_FOR_ACTOR` | Attack suite (with gateway off and on) |
| T05 | Privilege escalation | Viewer or Accountant calls an Approver action | Role check first in the pipeline | `ROLE_DENIED` | Unit |
| T06 | Cross-company access | Actor sends an ID that belongs to another company | Company check in gateway, then row-level security in PostgreSQL | `COMPANY_MISMATCH` | Unit + isolation test |
| T07 | Audit log edited or deleted | Someone changes or removes an entry | Append-only table, hash chain, verify function | `AUDIT_CHAIN_BROKEN` (on verify) | Unit + attack suite |
| T08 | Single approver on a large payment | Amount above threshold approved once | Two distinct approvers above the threshold | `NEEDS_SECOND_APPROVER` | Unit |
| T09 | Duplicate approver | Same person approves twice to reach two | Approvers counted by distinct ID | `DUPLICATE_APPROVER` | Unit |
| T10 | Replay of an old approval | Old signed approval reused for a new payment | Payload hash includes payment ID; approvals expire | `APPROVAL_EXPIRED` | Unit |
| T11 | Gateway outage used to bypass checks | Gateway timeout makes the API skip it | Fail closed: timeout or error means BLOCK | `GATEWAY_UNAVAILABLE` | Integration |
| T12 | Risky payment slips through | Duplicate invoice or anomalous amount | Risk score from the risk service; high score means HOLD | `HIGH_RISK` | Unit + integration |
| T13 | Policy tampering | Rule changed to weaken controls | `policies/` owned by Anan, changes by reviewed PR only | n/a | Code review |
| T14 | Secrets or bank data in logs | Sensitive values written to logs | Masking in structured logs | n/a | Unit (masking) |

## Open points
- Signature scheme: Ed25519 per approver (recommended) or HMAC with a server key.
- Approval expiry time.
- Who can confirm a bank-detail change (second Admin?).
- Behaviour when the risk service is down (proposal: HOLD).

## Feeds
These rows are the seed for Ziad's 100-case attack suite.
