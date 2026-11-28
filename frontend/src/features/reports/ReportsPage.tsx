// Owner: Karim
import { useState, type FormEvent } from 'react'
import { getCurrentUser } from '../../api/client'
import { formatDate, useLanguage, useT } from '../../app/i18n'
import { Badge, Card, PageHeader } from '../../shared/ui'
import { useAsync } from '../../shared/useAsync'
import ar from './locales/ar.json'
import en from './locales/en.json'
import { requestReport, type Report } from './reportsApi'

const messages = { ar, en }
const QUALITY_TONE = { passed: 'ok', numbers_checked: 'warn', fallback: 'neutral' } as const
const SUGGESTIONS = ['suggest.month', 'suggest.alerts', 'suggest.trend'] as const

function ReportView({ report }: { report: Report }) {
  const t = useT(messages)
  const { lang } = useLanguage()
  return (
    <article dir={report.language === 'ar' ? 'rtl' : 'ltr'} lang={report.language}>
      <Card>
        <h2 className="card__title">{report.title}</h2>
        <p className="muted small">
          {formatDate(report.date_from, lang)} – {formatDate(report.date_to, lang)}{' '}
          <Badge tone={QUALITY_TONE[report.quality]}>{t(`quality.${report.quality}`)}</Badge>
        </p>
        <p style={{ whiteSpace: 'pre-wrap' }}>{report.summary}</p>
      </Card>
      {report.sections.map((s) => (
        <Card key={s.key} title={s.heading}>
          <p style={{ whiteSpace: 'pre-wrap' }}>{s.body}</p>
        </Card>
      ))}
      <div className="no-print muted small">
        {report.notes.length > 0 && (
          <ul className="plain-list">
            {report.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        )}
        {Object.keys(report.models).length > 0 && (
          <p>
            {t('models')} {Object.entries(report.models).map(([m, n]) => `${m} ×${n}`).join(' · ')}
          </p>
        )}
      </div>
    </article>
  )
}

export function ReportsPage() {
  const t = useT(messages)
  const user = useAsync(() => getCurrentUser(), [])
  const [request, setRequest] = useState('')
  const [report, setReport] = useState<Report | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function generate(e: FormEvent) {
    e.preventDefault()
    if (!request.trim() || busy || user.status !== 'ready') return
    setBusy(true)
    setError(null)
    try {
      setReport(await requestReport(request.trim(), { id: user.data.id, role: user.data.role }))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="page">
      <PageHeader title={t('title')} subtitle={t('subtitle')}>
        {report && (
          <button type="button" className="btn btn--outline no-print" onClick={() => window.print()}>
            {t('print')}
          </button>
        )}
      </PageHeader>
      <form onSubmit={generate} className="row no-print">
        <label htmlFor="report-input" className="visually-hidden">
          {t('inputLabel')}
        </label>
        <input id="report-input" dir="auto" value={request} onChange={(e) => setRequest(e.target.value)}
               placeholder={t('placeholder')} maxLength={2000} disabled={busy} style={{ flex: 1 }} />
        <button type="submit" className="btn btn--primary" disabled={busy || !request.trim() || user.status !== 'ready'}>
          {busy ? t('working') : t('generate')}
        </button>
      </form>
      <p className="no-print">
        {SUGGESTIONS.map((k) => (
          <button key={k} type="button" className="btn btn--small btn--outline" onClick={() => setRequest(t(k))}>
            {t(k)}
          </button>
        ))}
      </p>
      {!report && !error && !busy && <p className="muted">{t('empty')}</p>}
      {error && (
        <p className="banner banner--danger" role="alert">
          {t('error')} <span className="muted">({error})</span>
        </p>
      )}
      {report && <ReportView report={report} />}
    </main>
  )
}
