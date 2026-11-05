import { Link } from 'react-router-dom'
import { useShellT } from './i18n'

export function NotFound() {
  const t = useShellT()
  return (
    <main className="page">
      <p>{t('notFound')}</p>
      <Link to="/" className="link">
        {t('backHome')}
      </Link>
    </main>
  )
}
