import type { ReactNode } from 'react'
import type { RiskLevel } from '../api/types'
import { useShellT } from '../app/i18n'

export function PageHeader({ title, subtitle, children }: { title: ReactNode; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <div className="page__head">
      <div className="page__heading">
        <h1 className="page__title">{title}</h1>
        {subtitle && <p className="page__subtitle">{subtitle}</p>}
      </div>
      {children}
    </div>
  )
}

export function Card({ title, actions, children, tone, className }: { title?: string; actions?: ReactNode; children: ReactNode; tone?: 'warn' | 'danger' | 'accent'; className?: string }) {
  return (
    <section className={['card', tone && `card--${tone}`, className].filter(Boolean).join(' ')}>
      {(title || actions) && (
        <div className="card__head">
          {title && <h2 className="card__title">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  )
}

export function Badge({ tone, children }: { tone: 'danger' | 'warn' | 'ok' | 'neutral'; children: ReactNode }) {
  return <span className={`badge badge--${tone}`}>{children}</span>
}

const RISK_TONE = { high: 'danger', medium: 'warn', low: 'ok' } as const

export function RiskBadge({ level }: { level: RiskLevel }) {
  const t = useShellT()
  return <Badge tone={RISK_TONE[level]}>{t(`risk.${level}`)}</Badge>
}

/** Codes, IBANs and invoice numbers are always left-to-right, even inside Arabic text. */
export function Ltr({ children }: { children: ReactNode }) {
  return (
    <bdi dir="ltr" className="ltr">
      {children}
    </bdi>
  )
}

export function Loading() {
  const t = useShellT()
  return (
    <p className="muted" role="status">
      {t('loading')}
    </p>
  )
}

export function LoadError({ error }: { error: Error }) {
  const t = useShellT()
  return (
    <p className="banner banner--danger" role="alert">
      {t('loadError')} <span className="muted">({error.message})</span>
    </p>
  )
}
