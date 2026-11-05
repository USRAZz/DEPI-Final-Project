import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getBankChange } from '../../api/client'
import type { AccountView } from '../../api/types'
import { useLanguage, useShellT, useT } from '../../app/i18n'
import { formatNumber, maskIban } from '../../shared/format'
import { Badge, Card, LoadError, Loading, Ltr } from '../../shared/ui'
import { useAsync } from '../../shared/useAsync'
import ar from './locales/ar.json'
import en from './locales/en.json'

const messages = { ar, en }

const CHECKS = ['calledKnownNumber', 'voiceConfirmed', 'bankLetter'] as const

function useNow(intervalMs: number) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}

export function BankChangePage() {
  const { vendorId = '' } = useParams()
  const t = useT(messages)
  const { lang } = useLanguage()
  const state = useAsync(() => getBankChange(Number(vendorId)), [vendorId])
  const now = useNow(30_000)
  const [done, setDone] = useState<Record<string, boolean>>({})
  const [outcome, setOutcome] = useState<'confirmed' | 'rejected' | null>(null)

  if (state.status === 'loading') return <main className="page"><Loading /></main>
  if (state.status === 'error') return <main className="page"><LoadError error={state.error} /></main>
  const { vendor, current, proposed, requested_by: requestedBy } = state.data

  if (!proposed) {
    return (
      <main className="page">
        <h1 className="page__title">{t('title')}</h1>
        <p className="muted">{t('noRequest')}</p>
      </main>
    )
  }

  const msLeft = proposed.hold_until ? Math.max(0, Date.parse(proposed.hold_until) - now) : 0
  const minutesLeft = Math.ceil(msLeft / 60_000)
  const hh = formatNumber(Math.floor(minutesLeft / 60), lang)
  const mm = new Intl.NumberFormat(lang === 'ar' ? 'ar-EG' : 'en-US', { minimumIntegerDigits: 2 }).format(minutesLeft % 60)
  const allChecked = CHECKS.every((c) => done[c])
  const canConfirm = allChecked && msLeft === 0

  return (
    <main className="page">
      <h1 className="page__title">
        {t('title')} <Badge tone="warn">{t('onHold')}</Badge>
      </h1>

      <Card>
        <div className="card__head">
          <div>
            <span className="muted">{t('vendor')}</span>
            <div style={{ fontSize: 20, fontWeight: 700 }}><bdi>{vendor.name}</bdi></div>
            <span className="muted small">{t('requestedBy', { name: requestedBy?.full_name })}</span>
          </div>
          <div className="hold" role="timer" aria-live="off">
            <span className="small" style={{ fontWeight: 700, color: 'var(--warn)' }}>{msLeft > 0 ? t('holdEndsIn') : t('holdEnded')}</span>
            <span className="hold__time"><bdi dir="ltr">{hh}:{mm}</bdi></span>
            <span className="muted small">{t('holdOf', { n: formatNumber(48, lang) })}</span>
          </div>
        </div>
      </Card>

      <div className="grid-auto" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))' }}>
        {current && <AccountCard account={current} label={t('current')} note={t('currentNote', { n: formatNumber(current.times_paid, lang) })} />}
        <AccountCard account={proposed} label={t('proposed')} note={t('proposedNote')} highlight />
      </div>

      <Card title={t('checks.title')}>
        {CHECKS.map((c) => (
          <div key={c} className="check">
            <input type="checkbox" id={c} checked={!!done[c]} onChange={(e) => setDone({ ...done, [c]: e.target.checked })} disabled={!!outcome} />
            <label htmlFor={c}>
              <strong>{t(`checks.${c}.title`)}</strong>
              <span className="muted small">{t(`checks.${c}.hint`)}</span>
            </label>
          </div>
        ))}
        {outcome ? (
          <p className="notice" role="status">{t(`outcome.${outcome}`)}</p>
        ) : (
          <div className="actions">
            <button type="button" className="btn btn--primary" disabled={!canConfirm} onClick={() => setOutcome('confirmed')}>{t('confirm')}</button>
            <button type="button" className="btn btn--danger" onClick={() => setOutcome('rejected')}>{t('reject')}</button>
            {!canConfirm && <span className="muted small">{t('confirmLocked')}</span>}
          </div>
        )}
      </Card>
    </main>
  )
}

function AccountCard({ account, label, note, highlight }: { account: AccountView; label: string; note: string; highlight?: boolean }) {
  const t = useShellT()
  return (
    <section className="card" style={highlight ? { border: '2px solid var(--warn-line)' } : undefined}>
      <span className="small" style={{ fontWeight: 700, color: highlight ? 'var(--warn)' : 'var(--muted)' }}>{label}</span>
      <strong>{t(`banks.${account.bank_name}`, { defaultValue: account.bank_name })}</strong>
      <span className="iban"><Ltr>{maskIban(account.iban)}</Ltr></span>
      <span className="small" style={{ fontWeight: 600, color: highlight ? 'var(--warn)' : 'var(--accent)' }}>{note}</span>
    </section>
  )
}
