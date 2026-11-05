import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from './App'
import { LanguageProvider } from './i18n'

function renderAt(path: string) {
  return render(
    <LanguageProvider>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </LanguageProvider>,
  )
}

describe('app shell', () => {
  it('opens in Arabic and switches to English', async () => {
    renderAt('/')
    expect(await screen.findByRole('heading', { name: 'لوحة التحكم' })).toBeInTheDocument()
    expect(document.documentElement.dir).toBe('rtl')

    await userEvent.click(screen.getByRole('button', { name: 'English' }))
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    expect(document.documentElement.dir).toBe('ltr')
  })

  it('lists pending payments with their risk', async () => {
    renderAt('/')
    expect(await screen.findByText('Nile Paper')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'مراجعة' })).toHaveLength(4)
  })

  it('keeps pages from other features in the sidebar and detail routes out of it', async () => {
    renderAt('/')
    const links = await screen.findAllByRole('link', { name: /الفواتير|الموافقات|لوحة الأمان/ })
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/invoices', '/approvals', '/security'])
  })

  it('shows the not-found page for an unknown path', async () => {
    renderAt('/no-such-page')
    expect(await screen.findByText('الصفحة دي مش موجودة.')).toBeInTheDocument()
  })
})

describe('payment approval', () => {
  it('shows the gateway hold and lets a different user approve', async () => {
    renderAt('/payments/187')
    expect(await screen.findByText('معلّق لحد الاعتماد')).toBeInTheDocument()
    const approve = screen.getByRole('button', { name: 'اعتماد وتوقيع' })
    expect(approve).toBeEnabled()
    await userEvent.click(approve)
    expect(screen.getByRole('status')).toHaveTextContent('اتسجّل اعتمادك')
  })
})

describe('invoice review', () => {
  it('flags a possible duplicate and a low-confidence field', async () => {
    renderAt('/invoices/412')
    expect(await screen.findByRole('alert')).toHaveTextContent('ممكن تكون فاتورة مكررة')
    expect(screen.getAllByText('مش متأكدين منها، راجعها')).toHaveLength(1)
  })
})

describe('bank account change', () => {
  // The sample account's hold ends at 2026-11-04T19:15Z.
  afterEach(() => {
    vi.useRealTimers()
  })

  async function tickAllChecks() {
    for (const box of screen.getAllByRole('checkbox')) await userEvent.click(box)
  }

  it('keeps confirm locked during the hold even when every check is done', async () => {
    vi.useFakeTimers({ now: new Date('2026-11-03T12:00:00Z'), shouldAdvanceTime: true })
    renderAt('/vendors/2/bank-change')
    const confirm = await screen.findByRole('button', { name: 'تأكيد الحساب الجديد' })
    await tickAllChecks()
    expect(confirm).toBeDisabled()
  })

  it('unlocks confirm after the hold once every check is done', async () => {
    vi.useFakeTimers({ now: new Date('2026-11-05T12:00:00Z'), shouldAdvanceTime: true })
    renderAt('/vendors/2/bank-change')
    const confirm = await screen.findByRole('button', { name: 'تأكيد الحساب الجديد' })
    expect(confirm).toBeDisabled()
    await tickAllChecks()
    expect(confirm).toBeEnabled()
  })
})
