// Owner: Yossra
import { useState, type FormEvent } from 'react'
import { getCurrentUser } from '../../api/client'
import { formatMoney, useLanguage, useT } from '../../app/i18n'
import { Badge, Card, Ltr, PageHeader, RiskBadge } from '../../shared/ui'
import { useAsync } from '../../shared/useAsync'
import { answerWithoutAlertBlock, sendChat, type ChatResponse, type ChatTurn, type InvoiceAlert } from './chatApi'
import ar from './locales/ar.json'
import en from './locales/en.json'

const messages = { ar, en }

type Entry = { question: string; response: ChatResponse | null; error: string | null }

function AlertCard({ alert }: { alert: InvoiceAlert }) {
  const t = useT(messages)
  return (
    <div className={`alert alert--${alert.level === 'high' ? 'danger' : 'warn'}`} role="note">
      <div className="alert__text">
        <span className="alert__title">
          {t('alert.invoice')} <Ltr>{alert.invoice_number ?? alert.invoice_id}</Ltr>
          {alert.vendor && <> · {alert.vendor}</>} {alert.level && <RiskBadge level={alert.level} />}
          {alert.score !== null && <span className="muted small"> {t('alert.score', { score: alert.score })}</span>}
        </span>
        <span className="muted small">{t('alert.why')}</span>
        <ul className="plain-list">
          {alert.reasons.map((r) => (
            <li key={r.code} className="reason">{r.text}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function Reply({ response }: { response: ChatResponse }) {
  const t = useT(messages)
  const { lang } = useLanguage()
  return (
    <>
      <p style={{ whiteSpace: 'pre-wrap' }} dir="auto">{answerWithoutAlertBlock(response.answer)}</p>
      {response.alerts.length > 0 && (
        <Card title={t('alerts.title')} tone="warn">
          <div className="alert-list">
            {response.alerts.map((a) => <AlertCard key={a.invoice_id} alert={a} />)}
          </div>
        </Card>
      )}
      {response.proposed_actions.map((p) => (
        <Card key={p.params.invoice_id} title={t('proposal.title')} tone="accent">
          <p>
            {t('proposal.text', { invoice: p.params.invoice_id })}{' '}
            <strong>{formatMoney(Number(p.params.amount), lang, p.params.currency)}</strong>
          </p>
          <p className="muted small">{t('proposal.needsApproval')}</p>
        </Card>
      ))}
      {response.sources.length > 0 && (
        <p className="muted small">
          {t('sources')} {response.sources.map((s) => <Badge key={s} tone="neutral">{t(`tool.${s}`, { defaultValue: s })}</Badge>)}
        </p>
      )}
    </>
  )
}

export function AgentPage() {
  const t = useT(messages)
  const user = useAsync(() => getCurrentUser(), [])
  const [entries, setEntries] = useState<Entry[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)

  async function ask(e: FormEvent) {
    e.preventDefault()
    const question = draft.trim()
    if (!question || busy || user.status !== 'ready') return
    const history: ChatTurn[] = entries.flatMap((x) =>
      x.response ? [{ role: 'user' as const, content: x.question }, { role: 'assistant' as const, content: x.response.answer }] : [],
    )
    setDraft('')
    setBusy(true)
    setEntries((list) => [...list, { question, response: null, error: null }])
    try {
      const response = await sendChat(question, history, { id: user.data.id, role: user.data.role })
      setEntries((list) => list.map((x, i) => (i === list.length - 1 ? { ...x, response } : x)))
    } catch (err) {
      const error = err instanceof Error ? err.message : String(err)
      setEntries((list) => list.map((x, i) => (i === list.length - 1 ? { ...x, error } : x)))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="page">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      {entries.length === 0 && <p className="muted">{t('empty')}</p>}
      {entries.map((x, i) => (
        <Card key={i}>
          <p className="eyebrow" dir="auto">{x.question}</p>
          {x.response && <Reply response={x.response} />}
          {!x.response && !x.error && <p className="muted" role="status">{t('thinking')}</p>}
          {x.error && <p className="banner banner--danger" role="alert">{t('error')} <span className="muted">({x.error})</span></p>}
        </Card>
      ))}
      <form onSubmit={ask} className="row">
        <label htmlFor="chat-input" className="visually-hidden">{t('inputLabel')}</label>
        <input id="chat-input" dir="auto" value={draft} onChange={(e) => setDraft(e.target.value)}
               placeholder={t('placeholder')} maxLength={4000} disabled={busy} style={{ flex: 1 }} />
        <button type="submit" className="btn btn--primary" disabled={busy || !draft.trim() || user.status !== 'ready'}>
          {t('send')}
        </button>
      </form>
      <p className="muted small">{t('readOnly')}</p>
    </main>
  )
}
