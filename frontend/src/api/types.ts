// TypeScript mirror of securefin_contracts and the views in services/api/app/schemas.py.
// Same field names. Once services/api is wired in, generate this file from its OpenAPI schema.

export type Currency = 'EGP' | 'USD' | 'EUR'
export type Role = 'admin' | 'approver' | 'accountant' | 'viewer'
export type RiskLevel = 'low' | 'medium' | 'high'
export type Decision = 'ALLOW' | 'PENDING_APPROVAL' | 'BLOCK'

export interface Money {
  amount: string // decimal string, never a float
  currency: Currency
}

export interface User {
  id: number
  full_name: string
  role: Role
  language: 'ar' | 'en'
}

export interface InvoiceData {
  vendor: string
  invoice_no: string
  date: string
  amount: string
  currency: string
  iban: string | null
  field_confidence: Record<string, number>
}

export type InvoiceStatus =
  | 'VALIDATED'
  | 'NEEDS-REVIEW'
  | 'FLAGGED'
  | 'VENDOR_CHANGE_PENDING'
  | 'PENDING_APPROVAL'
  | 'PAID_SIMULATED'
  | 'REJECTED'

export interface Invoice {
  id: number
  vendor_id: number | null
  source: 'upload' | 'email' | 'eta'
  status: InvoiceStatus
  fields: InvoiceData | null
  duplicate_of: number | null
  category: string | null
  created_at: string
}

export interface ShapReason {
  feature: string
  value: number | string
  contribution: number
}

export interface RiskScore {
  score: number
  level: RiskLevel
  rule_hits: string[]
  shap_reasons: ShapReason[]
}

export type PaymentRequestStatus = 'draft' | 'pending_approval' | 'approved' | 'blocked' | 'rejected' | 'exported'

export interface PaymentRequest {
  id: number
  vendor_id: number
  bank_account_id: number
  invoice_ids: number[]
  money: Money
  status: PaymentRequestStatus
  created_by: number
  created_at: string
}

export interface GatewayDecision {
  decision: Decision
  reasons: string[]
  risk_score: number | null
  required_approvers: number
}

export type BankAccountStatus = 'on_hold' | 'verified' | 'rejected'

export interface AccountView {
  id: number
  vendor_id: number
  bank_name: string
  iban: string
  status: BankAccountStatus
  hold_until: string | null
  times_paid: number
}

export interface Vendor {
  id: number
  name: string
}

export interface PendingRow {
  request: PaymentRequest
  vendor: Vendor
  created_by: User
  risk: RiskScore | null
}

export interface DashboardView {
  month_spend: Money
  invoices_paid: number
  pending_count: number
  above_limit_count: number
  flagged_count: number
  on_hold_count: number
  pending: PendingRow[]
}

export interface ApprovalView {
  approver: User
  approved: boolean
  signed_at: string
}

export interface PaymentRequestView {
  request: PaymentRequest
  vendor: Vendor
  account: AccountView
  created_by: User
  risk: RiskScore | null
  gateway: GatewayDecision
  approvals: ApprovalView[]
}

export interface BankChangeView {
  vendor: Vendor
  current: AccountView | null
  proposed: AccountView | null
  requested_by: User | null
}
