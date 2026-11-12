import { describe, expect, it } from 'vitest'
import { formatMoney, formatNumber, maskIban } from './format'

describe('formatMoney', () => {
  it('uses Arabic-Indic digits and the Egyptian pound sign in Arabic', () => {
    expect(formatMoney({ amount: '15400.00', currency: 'EGP' }, 'ar')).toBe('١٥٬٤٠٠٫٠٠ ج.م')
  })

  it('puts the currency code first in English', () => {
    expect(formatMoney({ amount: '15400.5', currency: 'EGP' }, 'en')).toBe('EGP 15,400.50')
  })
})

describe('formatNumber', () => {
  it('formats in the chosen language', () => {
    expect(formatNumber(72, 'ar')).toBe('٧٢')
    expect(formatNumber(72, 'en')).toBe('72')
  })
})

describe('maskIban', () => {
  it('shows the start and end of the IBAN in groups of four', () => {
    expect(maskIban('EG380019000500000000263180002')).toBe('EG38 0019 0005 •••• •••• •••1 8000 2')
  })
})
