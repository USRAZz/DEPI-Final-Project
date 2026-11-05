import type { ComponentType } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { getCurrentUser } from '../api/client'
import { BuildingIcon, CardIcon, FileIcon, GlobeIcon, GridIcon, LogIcon, ShieldIcon, SparkIcon } from '../shared/icons'
import { useAsync } from '../shared/useAsync'
import { useLanguage, useShellT } from './i18n'
import type { FeatureRoute } from './types'

const ICONS: Record<string, ComponentType> = {
  '/': GridIcon,
  '/invoices': FileIcon,
  '/payments/:requestId': CardIcon,
  '/vendors/:vendorId/bank-change': BuildingIcon,
  '/audit': LogIcon,
  '/assistant': SparkIcon,
  '/security': ShieldIcon,
}

function sidebarRoutes(routes: FeatureRoute[]) {
  return routes
    .filter((r) => r.navTo || !r.path.includes(':'))
    .sort((a, b) => (a.order ?? Infinity) - (b.order ?? Infinity))
}

export function Layout({ routes }: { routes: FeatureRoute[] }) {
  const t = useShellT()
  const { lang, setLang } = useLanguage()
  const user = useAsync(getCurrentUser, [])
  const nextLang = lang === 'ar' ? 'en' : 'ar'

  return (
    <div className="shell">
      <nav className="sidebar" aria-label={t('menu')}>
        <div className="sidebar__brand">
          <span className="sidebar__mark">
            <ShieldIcon size={18} />
          </span>
          <span>{t('appName')}</span>
        </div>
        {sidebarRoutes(routes).map((r) => {
          const ItemIcon = ICONS[r.path] ?? FileIcon
          return (
            <NavLink key={r.path} to={r.navTo ?? r.path} end={r.path === '/'} className="sidebar__link">
              <ItemIcon />
              {r.label[lang]}
            </NavLink>
          )
        })}
        <div className="sidebar__foot">{t('footer')}</div>
      </nav>

      <div className="shell__main">
        <header className="topbar">
          <span className="topbar__company">
            <BuildingIcon size={16} />
            {t('company')}
          </span>
          <div className="topbar__end">
            <button type="button" className="lang-toggle" lang={nextLang} onClick={() => setLang(nextLang)}>
              <GlobeIcon size={16} />
              {t('switchLanguage')}
            </button>
            {user.status === 'ready' && (
              <div className="user">
                <span className="user__avatar" aria-hidden="true">
                  {user.data.full_name
                    .split(' ')
                    .map((part) => part.charAt(0))
                    .slice(0, 2)
                    .join('')}
                </span>
                <span className="user__text">
                  <span className="user__name">{user.data.full_name}</span>
                  <span className="muted small">{t(`roles.${user.data.role}`)}</span>
                </span>
              </div>
            )}
          </div>
        </header>
        <Outlet />
      </div>
    </div>
  )
}
