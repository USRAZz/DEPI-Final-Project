import type { Currency, Money } from '../api/types'

const LOCALES = { ar: 'ar-EG', en: 'en-US' } as const

function locale(lang: string) {
  return lang === 'ar' ? LOCALES.ar : LOCALES.en
}

export function formatNumber(value: number, lang: string, fractionDigits = 0) {
  return new Intl.NumberFormat(locale(lang), {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value)
}

const CURRENCY_AR: Record<Currency, string> = { EGP: 'ج.م', USD: 'دولار', EUR: 'يورو' }

/** Money arrives from the API as a decimal string; it is only converted to a number for display. */
export function formatMoney(money: Money, lang: string) {
  const amount = formatNumber(Number(money.amount), lang, 2)
  return lang === 'ar' ? `${amount} ${CURRENCY_AR[money.currency]}` : `${money.currency} ${amount}`
}

export function formatDate(iso: string, lang: string) {
  return new Intl.DateTimeFormat(locale(lang), { dateStyle: 'medium' }).format(new Date(iso))
}

export function formatDateTime(iso: string, lang: string) {
  return new Intl.DateTimeFormat(locale(lang), { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso))
}

/** Groups an IBAN in fours and hides the middle, e.g. "EG38 0019 0005 •••• •••• •••1 8000 2". */
export function maskIban(iban: string) {
  const visible = iban.slice(0, 12) + '•'.repeat(iban.length - 18) + iban.slice(-6)
  return visible.replace(/(.{4})/g, '$1 ').trim()
}

/** A record id for people to read, e.g. displayId('PR', 187) gives "PR-0187". */
export function displayId(prefix: string, id: number) {
  return `${prefix}-${String(id).padStart(4, '0')}`
}
