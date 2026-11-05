import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { getDashboard } from '../../api/client'
import { useLanguage, useT } from '../../app/i18n'
import { formatDate, formatMoney, formatNumber } from '../../shared/format'
import { AlertIcon, ClockIcon, FileIcon, LockIcon, WalletIcon } from '../../shared/icons'
import { Card, LoadError, Loading, PageHeader, RiskBadge } from '../../shared/ui'
import { useAsync } from '../../shared/useAsync'
import ar from './locales/ar.json'
import en from './locales/en.json'

const messages = { ar, en }

function Kpi({ label, value, icon, tone, foot }: { label: string; value: string; icon: ReactNode; tone?: 'warn' | 'danger'; foot: ReactNode }) {
  return (
    <Card className="kpi">
      <div className="kpi__top">
        <span className="kpi__label">{label}</span>
        <span className={`kpi__icon${tone ? ` kpi__icon--${tone}` : ''}`}>{icon}</span>
      </div>
      <span className="kpi__value">{value}</span>
      <div className="kpi__foot">{foot}</div>
    </Card>
  )
}

export function DashboardPage() {
  const t = useT(messages)
  const { lang } = useLanguage()
  const state = useAsync(getDashboard, [])
  const [today] = useState(() => new Date().toISOString())

  if (state.status === 'loading') return <main className="page"><Loading /></main>
  if (state.status === 'error') return <main className="page"><LoadError error={state.error} /></main>
  const d = state.data
  const n = (value: number) => formatNumber(value, lang)

  return (
    <main className="page">
      <PageHeader title={t('title')} subtitle={t('subtitle', { date: formatDate(today, lang) })} />

      <div className="grid-auto">
        <Kpi
          label={t('kpi.spent')}
          value={formatMoney(d.month_spend, lang)}
          icon={<WalletIcon />}
          foot={<span className="muted">{t('kpi.spentNote', { count: d.invoices_paid, n: n(d.invoices_paid) })}</span>}
        />
        <Kpi
          label={t('kpi.pending')}
          value={n(d.pending_count)}
          icon={<ClockIcon />}
          tone="warn"
          foot={<span className="text-warn">{t('kpi.pendingNote', { n: n(d.above_limit_count) })}</span>}
        />
        <Kpi
          label={t('kpi.flagged')}
          value={n(d.flagged_count)}
          icon={<FileIcon />}
          tone="danger"
          foot={<Link to="/invoices/412" className="link">{t('kpi.flaggedNote')}</Link>}
        />
        <Kpi
          label={t('kpi.onHold')}
          value={n(d.on_hold_count)}
          icon={<LockIcon />}
          foot={<Link to="/vendors/2/bank-change" className="link">{t('kpi.onHoldNote')}</Link>}
        />
      </div>

      <div className="row">
        <div className="col-wide">
          <Card title={t('pending.title')} className="card--flush">
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">{t('pending.vendor')}</th>
                    <th scope="col">{t('pending.amount')}</th>
                    <th scope="col">{t('pending.requestedBy')}</th>
                    <th scope="col">{t('pending.risk')}</th>
                    <th scope="col" className="cell-end"><span className="visually-hidden">{t('pending.action')}</span></th>
                  </tr>
                </thead>
                <tbody>
                  {d.pending.map((row) => (
                    <tr key={row.request.id}>
                      <td>
                        <span className="vendor">
                          <span className="vendor__mark" aria-hidden="true">{row.vendor.name.charAt(0)}</span>
                          <bdi>{row.vendor.name}</bdi>
                        </span>
                      </td>
                      <td className="num"><strong>{formatMoney(row.request.money, lang)}</strong></td>
                      <td className="muted">{row.created_by.full_name}</td>
                      <td>{row.risk && <RiskBadge level={row.risk.level} />}</td>
                      <td className="cell-end">
                        <Link to={`/payments/${row.request.id}`} className="btn btn--outline btn--small">
                          {t('pending.review')}
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        <div className="col-narrow">
          <Card title={t('alerts.title')} className="card--flush">
            <div className="alert-list">
              <Link to="/invoices/412" className="alert alert--danger">
                <span className="alert__icon"><AlertIcon size={16} /></span>
                <span className="alert__text">
                  <span className="alert__title">{t('alerts.duplicateTitle')}</span>
                  <span className="muted small">{t('alerts.duplicateBody')}</span>
                </span>
              </Link>
              <Link to="/vendors/2/bank-change" className="alert alert--warn">
                <span className="alert__icon"><LockIcon size={16} /></span>
                <span className="alert__text">
                  <span className="alert__title">{t('alerts.bankTitle')}</span>
                  <span className="muted small">{t('alerts.bankBody')}</span>
                </span>
              </Link>
            </div>
          </Card>
        </div>
      </div>
    </main>
  )
}
