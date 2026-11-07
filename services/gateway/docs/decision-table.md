# SecureFin Gateway: Decision Table

Owner: Anan Alaa. Status: draft v0.1.

## How the pipeline runs
Checks run in this order. The first BLOCK stops the pipeline. HOLD reasons are collected and returned together.

1. Authentication and request validity
2. Role permission
3. Company isolation
4. Action-specific rules
5. Policy values from `policies/`
6. Risk score
7. Final outcome and audit entry

A decision is always written to the audit log, whatever the outcome.

## Rules

| # | Rule | Condition | Outcome | Reason code |
| --- | --- | --- | --- | --- |
| 1 | Invalid request | Missing or malformed fields | BLOCK | `INVALID_REQUEST` |
| 2 | Not authenticated | No valid actor | BLOCK | `NOT_AUTHENTICATED` |
| 3 | Role denied | Actor's role is not allowed for this action | BLOCK | `ROLE_DENIED` |
| 4 | Company mismatch | Any referenced object belongs to another company | BLOCK | `COMPANY_MISMATCH` |
| 5 | Assistant tries to execute | Actor is the assistant and the action is approve or execute | BLOCK | `ACTION_NOT_ALLOWED_FOR_ACTOR` |
| 6 | Self-approval | Approver ID equals the payment creator ID | BLOCK | `SELF_APPROVAL` |
| 7 | Duplicate approver | The same approver already approved this payment | BLOCK | `DUPLICATE_APPROVER` |
| 8 | Payload mismatch | Payload hash differs from what was signed | BLOCK | `APPROVAL_PAYLOAD_MISMATCH` |
| 9 | Approval expired | Approval older than the expiry limit | BLOCK | `APPROVAL_EXPIRED` |
| 10 | Not enough approvals | Execute requested without required approvals | BLOCK | `APPROVALS_MISSING` |
| 11 | Needs second approver | Amount at or above `two_approver_threshold` and fewer than 2 approvals | HOLD | `NEEDS_SECOND_APPROVER` |
| 12 | Bank change cooling | Vendor bank details changed less than `bank_change_hold_hours` ago | HOLD | `BANK_CHANGE_COOLING` |
| 13 | Bank change unconfirmed | Bank change not yet confirmed | HOLD | `BANK_CHANGE_UNCONFIRMED` |
| 14 | High risk | Risk score at or above `risk_hold_score` | HOLD | `HIGH_RISK` |
| 15 | Risk unavailable | Risk service did not answer | HOLD | `RISK_UNAVAILABLE` |
| 16 | Gateway failure | Timeout or internal error | BLOCK | `GATEWAY_UNAVAILABLE` |
| 17 | All checks pass | None of the above | ALLOW | `OK` |

## Policy values (in `policies/`, not in code)

| Name | Starting value |
| --- | --- |
| `two_approver_threshold` | EGP 10,000 |
| `bank_change_hold_hours` | 48 |
| `approval_expiry_hours` | 72 |
| `risk_hold_score` | 0.7 |

These are assumptions (no real client), stored in `policies/defaults.yaml`. The loader refuses a policy that lets the gateway fail open, lets creators approve, or lets the assistant execute.

## Who may do what (first draft)

| Action | Viewer | Accountant | Approver | Admin | Assistant |
| --- | --- | --- | --- | --- | --- |
| `create_payment_request` | no | yes | yes | yes | propose only |
| `approve_payment` | no | no | yes | yes | no |
| `execute_payment` | no | no | no | yes (after ALLOW) | no |
| `change_vendor_bank_details` | no | yes (starts hold) | no | yes | propose only |
| `confirm_bank_change` | no | no | yes | yes | no |
| `export_payment_file` | no | no | yes | yes | no |
| `read_audit_log` | no | no | yes | yes | no |
| `verify_audit_log` | no | no | yes | yes | no |

Note: "propose only" means the assistant's request is judged like a user's, using the logged-in user's own role, and it can never be the final step.

## Implementation notes (v0.2)
- Rules 6 to 13 are applied at the action where they matter: `approve_payment` checks rules 6 and 7; `execute_payment` checks rules 8 to 15.
- Low risk does not skip approvals. A payment executes only with the required valid approvals, whatever its risk score.
- Currency other than EGP always needs two approvers (the threshold is in EGP).
- `confirm_bank_change` by the person who requested the change is blocked (`SELF_APPROVAL`).
- Any approval whose payload hash differs from the current payment blocks execution, even if other approvals are valid.
- Signature verification (not only the hash) is added in the signing step (weeks 6 to 7).
- Rules 10 and 11 at execution: no valid approval at all is BLOCK (`APPROVALS_MISSING`, or `APPROVAL_EXPIRED` if only stale approvals exist). At least one valid approval but fewer than required is HOLD (`NEEDS_SECOND_APPROVER`).
- The gateway uses its own clock for expiry and hold periods. `requested_at` from the caller is never used for timing.
- `change_vendor_bank_details` is never final: it always returns HOLD (rules 12 and 13) with `hold_until`. A second person releases it with `confirm_bank_change`.
- `create_payment_request` must name the acting user as `created_by`. Otherwise the self-approval rule could be dodged later.
- `execute_payment` needs the vendor's bank-detail state from the API. If it is missing the request is `INVALID_REQUEST`; the gateway does not guess.
- Authentication is checked first, then request validity, then the role.

## Translation keys
Each reason code maps to a key like `gateway.reason.SELF_APPROVAL`, with text in `ar.json` and `en.json`. The gateway returns keys, never text.
