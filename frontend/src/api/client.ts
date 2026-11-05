// The only place pages get data from. Today it reads mock.ts and returns the same shapes as
// services/api; to connect it, each function becomes a call to `api()` on the same-named endpoint.
import * as mock from './mock'
import type { BankChangeView, DashboardView, Invoice, PaymentRequestView, User } from './types'

const DUAL_APPROVAL_LIMIT = 10_000 // EGP; to be confirmed at kickoff

function respond<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(structuredClone(value)), 150))
}

function notFound(what: string): never {
  throw new Error(`${what} not found`)
}

const userById = (id: number) => mock.users.find((u) => u.id === id) ?? notFound('user')
const vendorById = (id: number) => mock.vendors.find((v) => v.id === id) ?? notFound('vendor')

export async function getCurrentUser(): Promise<User> {
  return respond(userById(mock.currentUserId))
}

export async function getDashboard(): Promise<DashboardView> {
  const pending = mock.paymentRequests.filter((p) => p.status === 'pending_approval')
  return respond({
    month_spend: mock.monthSpend,
    invoices_paid: mock.invoicesPaid,
    pending_count: pending.length,
    above_limit_count: pending.filter((p) => Number(p.money.amount) > DUAL_APPROVAL_LIMIT).length,
    flagged_count: mock.invoices.filter((i) => i.status === 'FLAGGED').length,
    on_hold_count: mock.bankAccounts.filter((b) => b.status === 'on_hold').length,
    pending: pending.map((p) => ({
      request: p,
      vendor: vendorById(p.vendor_id),
      created_by: userById(p.created_by),
      risk: mock.risk[p.id] ?? null,
    })),
  })
}

export async function getInvoice(id: number): Promise<Invoice> {
  const invoice = mock.invoices.find((i) => i.id === id) ?? notFound('invoice')
  return respond(invoice)
}

export async function getPaymentRequest(id: number): Promise<PaymentRequestView> {
  const request = mock.paymentRequests.find((p) => p.id === id) ?? notFound('payment request')
  const account = mock.bankAccounts.find((b) => b.id === request.bank_account_id) ?? notFound('bank account')
  const required = Number(request.money.amount) > DUAL_APPROVAL_LIMIT ? 2 : 1
  return respond({
    request,
    vendor: vendorById(request.vendor_id),
    account,
    created_by: userById(request.created_by),
    risk: mock.risk[id] ?? null,
    gateway: mock.gateway[id] ?? { decision: 'PENDING_APPROVAL', reasons: [], risk_score: mock.risk[id]?.score ?? null, required_approvers: required },
    approvals: (mock.approvals[id] ?? []).map(({ approver_id, ...rest }) => ({ ...rest, approver: userById(approver_id) })),
  })
}

export async function getBankChange(vendorId: number): Promise<BankChangeView> {
  const accounts = mock.bankAccounts.filter((b) => b.vendor_id === vendorId)
  const requestedBy = mock.bankChangeRequestedBy[vendorId]
  return respond({
    vendor: vendorById(vendorId),
    current: accounts.find((b) => b.status === 'verified') ?? null,
    proposed: accounts.find((b) => b.status === 'on_hold') ?? null,
    requested_by: requestedBy ? userById(requestedBy) : null,
  })
}
