import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { getInvoice } from '../../api/client'
import type { InvoiceData } from '../../api/types'
import { useLanguage, useT } from '../../app/i18n'
import { formatNumber } from '../../shared/format'
import { AlertIcon } from '../../shared/icons'
import { Badge, Card, LoadError, Loading, Ltr } from '../../shared/ui'
import { useAsync } from '../../shared/useAsync'
import ar from './locales/review.ar.json'
import en from './locales/review.en.json'

const messages = { ar, en }

const LOW_CONFIDENCE = 0.8

type FieldKey = 'invoice_no' | 'date' | 'vendor' | 'amount' | 'iban'

// Codes and amounts are typed left-to-right even in the Arabic UI.
const FIELDS: { key: FieldKey; ltr?: boolean }[] = [
  { key: 'invoice_no', ltr: true },
  { key: 'date', ltr: true },
  { key: 'vendor' },
  { key: 'amount', ltr: true },
  { key: 'iban', ltr: true },
]

export function InvoiceReviewPage() {
  const { invoiceId = '' } = useParams()
  const t = useT(messages)
  const { lang } = useLanguage()
  const state = useAsync(() => getInvoice(Number(invoiceId)), [invoiceId])
  const [outcome, setOutcome] = useState<'saved' | 'notDuplicate' | 'rejected' | null>(null)

  if (state.status === 'loading') return <main className="page"><Loading /></main>
  if (state.status === 'error') return <main className="page"><LoadError error={state.error} /></main>
  const invoice = state.data
  const fields = invoice.fields
  const confidence = fields ? Math.min(...Object.values(fields.field_confidence), 1) : 1

  return (
    <main className="page">
      <div className="page__head">
        <h1 className="page__title">
          {t('title')} {fields && <Ltr>{fields.invoice_no}</Ltr>}
          <Badge tone={invoice.status === 'FLAGGED' ? 'danger' : 'neutral'}>{t(`status.${invoice.status}`)}</Badge>
        </h1>
      </div>

      <div className="row">
        <div className="col-narrow">
          <Card title={t('preview')} actions={<span className="muted small">{t(`source.${invoice.source}`)}</span>}>
            <div className="preview muted">{t('previewPlaceholder')}</div>
          </Card>
        </div>

        <div className="col-wide">
          {invoice.duplicate_of && (
            <div className="banner banner--danger" role="alert">
              <span className="text-danger"><AlertIcon /></span>
              <span className="alert__text">
                <span className="banner__title">{t('duplicate.title')}</span>
                <span>{t('duplicate.body')}</span>
              </span>
            </div>
          )}

          <Card title={t('fields.title')} actions={fields && <span className="muted small">{t('fields.confidence', { value: formatNumber(Math.round(confidence * 100), lang) })}</span>}>
            {fields ? (
              <form className="grid-2" onSubmit={(e) => e.preventDefault()}>
                {FIELDS.map(({ key, ltr }) => (
                  <FieldInput key={key} name={key} ltr={ltr} fields={fields} lang={lang} label={t(`fields.${key}`)} lowHint={t('fields.lowConfidence')} />
                ))}
              </form>
            ) : (
              <p className="muted">{t('fields.none')}</p>
            )}

            {outcome ? (
              <p className="notice" role="status">{t(`outcome.${outcome}`)}</p>
            ) : (
              <div className="actions">
                <button type="button" className="btn btn--primary" onClick={() => setOutcome('saved')}>{t('actions.save')}</button>
                {invoice.duplicate_of && (
                  <button type="button" className="btn btn--outline" onClick={() => setOutcome('notDuplicate')}>{t('actions.notDuplicate')}</button>
                )}
                <button type="button" className="btn btn--danger" onClick={() => setOutcome('rejected')}>{t('actions.reject')}</button>
              </div>
            )}
          </Card>
        </div>
      </div>
    </main>
  )
}

function FieldInput({ name, ltr, fields, lang, label, lowHint }: { name: FieldKey; ltr?: boolean; fields: InvoiceData; lang: string; label: string; lowHint: string }) {
  const raw = fields[name] ?? ''
  // A missing value is always flagged, whatever the confidence.
  const low = !raw || (fields.field_confidence[name] ?? 1) < LOW_CONFIDENCE
  const id = `field-${name}`
  return (
    <div className={`field${low ? ' field--low' : ''}`}>
      <label htmlFor={id}>{label}</label>
      <input id={id} name={name} defaultValue={raw} dir={ltr ? 'ltr' : 'auto'} style={ltr && lang === 'ar' ? { textAlign: 'right' } : undefined} />
      {low && <span className="field__hint">{lowHint}</span>}
    </div>
  )
}
