// Sample data matching services/api/app/store.py. Every IBAN here is fake.
import type { AccountView, GatewayDecision, Invoice, Money, PaymentRequest, RiskScore, User, Vendor } from './types'

export const users: User[] = [
  { id: 1, full_name: 'Karim Ashraf', role: 'admin', language: 'ar' },
  { id: 2, full_name: 'Mona', role: 'approver', language: 'ar' },
  { id: 3, full_name: 'Sara', role: 'accountant', language: 'ar' },
  { id: 4, full_name: 'Omar', role: 'accountant', language: 'ar' },
]

export const currentUserId = 1

export const vendors: Vendor[] = [
  { id: 1, name: 'Nile Paper' },
  { id: 2, name: 'Egyptian Packaging' },
  { id: 3, name: 'Cairo Net' },
  { id: 4, name: 'Al Amal Transport' },
]

export const bankAccounts: AccountView[] = [
  { id: 1, vendor_id: 1, bank_name: 'NBE', iban: 'EG380019000500000000263180002', status: 'verified', hold_until: null, times_paid: 9 },
  { id: 2, vendor_id: 2, bank_name: 'NBE', iban: 'EG430019000500000000263180009', status: 'verified', hold_until: null, times_paid: 14 },
  { id: 3, vendor_id: 2, bank_name: 'BM', iban: 'EG670037012400000000017907115', status: 'on_hold', hold_until: '2026-11-04T19:15:00Z', times_paid: 0 },
  { id: 4, vendor_id: 3, bank_name: 'CIB', iban: 'EG030010000000000100012345678', status: 'verified', hold_until: null, times_paid: 22 },
  { id: 5, vendor_id: 4, bank_name: 'NBE', iban: 'EG450019000500000000099112233', status: 'verified', hold_until: null, times_paid: 5 },
]

export const bankChangeRequestedBy: Record<number, number> = { 2: 4 }

export const invoices: Invoice[] = [
  {
    id: 412,
    vendor_id: 1,
    source: 'upload',
    status: 'FLAGGED',
    duplicate_of: 371,
    category: 'materials',
    created_at: '2026-11-02T09:10:00Z',
    fields: {
      vendor: 'Nile Paper',
      invoice_no: 'INV-2026-0412',
      date: '2026-10-28',
      amount: '15400.00',
      currency: 'EGP',
      iban: 'EG380019000500000000263180002',
      field_confidence: { vendor: 0.98, invoice_no: 0.97, date: 0.95, amount: 0.93, iban: 0.72 },
    },
  },
]

export const paymentRequests: PaymentRequest[] = [
  { id: 187, vendor_id: 1, bank_account_id: 1, invoice_ids: [412], money: { amount: '15400.00', currency: 'EGP' }, status: 'pending_approval', created_by: 3, created_at: '2026-11-02T10:00:00Z' },
  { id: 188, vendor_id: 2, bank_account_id: 2, invoice_ids: [415], money: { amount: '8750.00', currency: 'EGP' }, status: 'pending_approval', created_by: 3, created_at: '2026-11-02T11:30:00Z' },
  { id: 189, vendor_id: 3, bank_account_id: 4, invoice_ids: [416], money: { amount: '2300.00', currency: 'EGP' }, status: 'pending_approval', created_by: 4, created_at: '2026-11-03T08:05:00Z' },
  { id: 190, vendor_id: 4, bank_account_id: 5, invoice_ids: [417], money: { amount: '12000.00', currency: 'EGP' }, status: 'pending_approval', created_by: 4, created_at: '2026-11-03T08:40:00Z' },
]

export const risk: Record<number, RiskScore> = {
  187: {
    score: 72,
    level: 'high',
    rule_hits: ['DUPLICATE_INVOICE', 'AMOUNT_ABOVE_VENDOR_AVERAGE', 'FIRST_PAYMENT_THIS_QUARTER'],
    shap_reasons: [
      { feature: 'DUPLICATE_INVOICE', value: 1, contribution: 45 },
      { feature: 'AMOUNT_ABOVE_VENDOR_AVERAGE', value: 2.3, contribution: 20 },
      { feature: 'FIRST_PAYMENT_THIS_QUARTER', value: 1, contribution: 7 },
    ],
  },
  188: { score: 41, level: 'medium', rule_hits: [], shap_reasons: [] },
  189: { score: 8, level: 'low', rule_hits: [], shap_reasons: [] },
  190: { score: 12, level: 'low', rule_hits: [], shap_reasons: [] },
}

export const gateway: Record<number, GatewayDecision> = {
  187: { decision: 'PENDING_APPROVAL', reasons: ['ABOVE_DUAL_APPROVAL_LIMIT', 'HIGH_RISK'], risk_score: 72, required_approvers: 2 },
}

export const approvals: Record<number, { approver_id: number; approved: boolean; signed_at: string }[]> = {
  187: [{ approver_id: 2, approved: true, signed_at: '2026-11-03T08:42:00Z' }],
}

export const monthSpend: Money = { amount: '486250.00', currency: 'EGP' }
export const invoicesPaid = 38
