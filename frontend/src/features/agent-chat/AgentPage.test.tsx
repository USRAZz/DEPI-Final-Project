import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { LanguageProvider } from '../../app/i18n'
import { AgentPage } from './AgentPage'
import { answerWithoutAlertBlock } from './chatApi'

const REPLY = {
  answer: 'Invoice 3 is flagged.\n\nWhy these invoices have alerts:\n- Invoice A-1001: duplicate',
  proposed_actions: [],
  alerts: [{ invoice_id: 3, invoice_number: 'A-1001', vendor: 'Nile Office Supplies', status: 'FLAGGED', level: 'high',
             score: 70, reasons: [{ code: 'DUPLICATE_INVOICE', text: 'Same vendor and invoice number as an earlier one.' }] }],
  sources: ['get_invoices'],
}

afterEach(() => vi.unstubAllGlobals())

describe('assistant page', () => {
  it('sends the question with the user and shows each alert with its reason', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => REPLY })
    vi.stubGlobal('fetch', fetchMock)
    localStorage.setItem('securefin.lang', 'en')
    render(<LanguageProvider><AgentPage /></LanguageProvider>)

    await userEvent.type(await screen.findByLabelText('Your question'), 'Which invoices are flagged?')
    const send = screen.getByRole('button', { name: 'Send' })
    await waitFor(() => expect(send).toBeEnabled()) // the signed-in user has loaded
    await userEvent.click(send)

    expect(await screen.findByText('Same vendor and invoice number as an earlier one.')).toBeInTheDocument()
    expect(screen.getByText('Invoice 3 is flagged.')).toBeInTheDocument()
    expect(screen.queryByText(/Why these invoices have alerts/)).not.toBeInTheDocument() // shown as cards instead
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/chat')
    expect(init.headers['X-User-Id']).toBe('1')
    expect(JSON.parse(init.body)).toEqual({ message: 'Which invoices are flagged?', history: [] })
  })

  it('cuts only the alert block from the answer', () => {
    expect(answerWithoutAlertBlock('Hi.\n\nسبب التنبيهات:\n- x')).toBe('Hi.')
    expect(answerWithoutAlertBlock('No alerts here.')).toBe('No alerts here.')
  })
})
