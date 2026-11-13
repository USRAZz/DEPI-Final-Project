import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getCurrentUser, getPaymentRequest } from '../../api/client'
import { useLanguage, useShellT, useT } from '../../app/i18n'
import { displayId, formatDateTime, formatMoney, formatNumber, maskIban } from '../../shared/format'
import { Badge, Card, LoadError, Loading, Ltr, RiskBadge } from '../../shared/ui'
import { useAsync } from '../../shared/useAsync'
import ar from './locales/ar.json'
import en from './locales/en.json'

const messages = { ar, en }

export function PaymentApprovalPage() {
  const { requestId = '' } = useParams()
  const t = useT(messages)
  const shared = useShellT()
  const { lang } = useLanguage()
  const state = useAsync(() => Promise.all([getPaymentRequest(Number(requestId)), getCurrentUser()]), [requestId])
  const [outcome, setOutcome] = useState<'approved' | 'rejected' | null>(null)

  if (state.status === 'loading') return <main className="page"><Loading /></main>
  if (state.status === 'error') return <main className="page"><LoadError error={state.error} /></main>
  const [{ request, vendor, account, created_by: createdBy, risk, gateway, approvals }, me] = state.data
  const amount = formatMoney(request.money, lang)
  // Maker-checker: whoever created the request cannot approve it. The gateway enforces
  // this too; the UI only avoids offering a button that would be refused.
  const isCreator = request.created_by === me.id
  const alreadyApproved = approvals.some((a) => a.approver.id === me.id)
  const canApprove = !isCreator && !alreadyApproved && request.status === 'pending_approval'
  const required = gateway.required_approvers

  return (
    <main className="page">
      <div className="page__head">
        <h1 className="page__title">
          {t('title')} <Ltr>{displayId('PR', request.id)}</Ltr>
          <Badge tone="warn">{t(`status.${request.status}`)}</Badge>
        </h1>
      </div>

      <div className="row">
        <div className="col-wide">
          <Card>
            <div className="card__head" style={{ alignItems: 'flex-end' }}>
              <div>
                <span className="muted">{t('payTo')}</span>
                <div style={{ fontSize: 20, fontWeight: 700 }}><bdi>{vendor.name}</bdi></div>
              </div>
              <span className="amount-lg">{amount}</span>
            </div>
            <dl className="facts">
              <div>
                <dt>{t('facts.invoices')}</dt>
                <dd>{request.invoice_ids.map((id) => <Link key={id} to={`/invoices/${id}`} className="link"><Ltr>{displayId('INV', id)}</Ltr></Link>)}</dd>
              </div>
              <div>
                <dt>{t('facts.requestedBy')}</dt>
                <dd>{createdBy.full_name}</dd>
              </div>
              <div>
                <dt>{t('facts.bank')}</dt>
                <dd>{shared(`banks.${account.bank_name}`, { defaultValue: account.bank_name })}</dd>
              </div>
              <div>
                <dt>{t('facts.account')}</dt>
                <dd>{t(`accountStatus.${account.status}`)} · {t('facts.timesPaid', { n: formatNumber(account.times_paid, lang) })}</dd>
              </div>
            </dl>
          </Card>

          {risk && (
            <Card title={t('risk.title')} actions={<span><RiskBadge level={risk.level} /> <span className="num">{formatNumber(risk.score, lang)} / {formatNumber(100, lang)}</span></span>}>
              <div className="meter" role="img" aria-label={`${risk.score} / 100`}>
                <div className="meter__fill" style={{ width: `${risk.score}%` }} />
              </div>
              <ul className="plain-list">
                {risk.shap_reasons.map((r) => (
                  <li key={r.feature} className="reason">
                    <span>{t(`risk.reasons.${r.feature}`, { defaultValue: r.feature })}</span>
                    <span className="muted"><Ltr>+{formatNumber(r.contribution, lang)}</Ltr></span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        <div className="col-narrow">
          <Card tone={gateway.decision === 'BLOCK' ? 'danger' : 'warn'}>
              <span className="small" style={{ fontWeight: 700, color: 'var(--warn)' }}>{t('gateway.title')}</span>
              <strong style={{ fontSize: 18 }}>{t(`gateway.decision.${gateway.decision}`)}</strong>
              <ul className="plain-list" style={{ gap: 4 }}>
                {gateway.reasons.map((code) => <li key={code}>{t(`gateway.reasons.${code}`, { defaultValue: code })}</li>)}
              </ul>
            </Card>

          <Card title={t('chain.title', { n: formatNumber(required, lang) })}>
            <ol className="plain-list" style={{ gap: 10 }}>
              <li className="step">
                <span className="step__dot" aria-hidden="true">·</span>
                <span><strong>{createdBy.full_name}</strong><br /><span className="muted small">{t('chain.creator')}</span></span>
              </li>
              {approvals.map((a) => (
                <li key={a.approver.id} className="step">
                  <span className="step__dot step__dot--done" aria-hidden="true">✓</span>
                  <span><strong>{a.approver.full_name}</strong><br /><span className="muted small">{t('chain.approvedAt', { at: formatDateTime(a.signed_at, lang) })}</span></span>
                </li>
              ))}
              {approvals.length < required && (
                <li className="step">
                  <span className="step__dot step__dot--waiting" aria-hidden="true">{formatNumber(approvals.length + 1, lang)}</span>
                  <span><strong>{t('chain.you')}</strong><br /><span className="muted small">{t('chain.waiting')}</span></span>
                </li>
              )}
            </ol>
          </Card>

          <Card tone="accent" title={t('sign.title')}>
            <div className="signed">
              <span><strong>{t('sign.amount')}</strong> <span className="num">{amount}</span></span>
              <span><strong>{t('sign.account')}</strong> <Ltr>{maskIban(account.iban)}</Ltr></span>
            </div>
            <p className="muted small">{t('sign.note')}</p>
            {outcome ? (
              <p className="notice" role="status">{t(`sign.${outcome}`)}</p>
            ) : (
              <div className="actions">
                <button type="button" className="btn btn--primary" disabled={!canApprove} onClick={() => setOutcome('approved')}>{t('sign.approve')}</button>
                <button type="button" className="btn btn--danger" disabled={!canApprove} onClick={() => setOutcome('rejected')}>{t('sign.reject')}</button>
              </div>
            )}
            {isCreator && <p className="small" style={{ color: 'var(--warn)' }}>{t('sign.creatorCannotApprove')}</p>}
          </Card>
        </div>
      </div>
    </main>
  )
}
