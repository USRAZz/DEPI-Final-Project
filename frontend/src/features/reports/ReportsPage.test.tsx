import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { LanguageProvider } from '../../app/i18n'
import { ReportsPage } from './ReportsPage'

const REPORT = {
  title: 'October 2026 spending', language: 'en', date_from: '2026-10-01', date_to: '2026-10-31',
  summary: '15,900 EGP was paid.', rounds: 1, quality: 'passed', notes: [], models: { 'google/gemini-2.5-flash': 4 },
  markdown: '', sections: [{ key: 'spending_summary', heading: 'Spending', body: 'Paid 15,900 EGP.', facts: {} }],
}

afterEach(() => vi.unstubAllGlobals())

describe('reports page', () => {
  it('asks the api for a report and shows its sections, quality and models', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => REPORT })
    vi.stubGlobal('fetch', fetchMock)
    localStorage.setItem('securefin.lang', 'en')
    render(<LanguageProvider><ReportsPage /></LanguageProvider>)

    await userEvent.type(screen.getByLabelText('Report request'), 'October report')
    const create = screen.getByRole('button', { name: 'Create report' })
    await waitFor(() => expect(create).toBeEnabled())
    await userEvent.click(create)

    expect(await screen.findByText('Paid 15,900 EGP.')).toBeInTheDocument()
    expect(screen.getByText('Checked')).toBeInTheDocument()
    expect(screen.getByText(/google\/gemini-2.5-flash ×4/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Print / save as PDF' })).toBeInTheDocument()
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/reports')
    expect(JSON.parse(init.body)).toEqual({ request: 'October report' })
  })
})
