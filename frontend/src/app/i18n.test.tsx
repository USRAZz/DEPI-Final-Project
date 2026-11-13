import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { LanguageProvider, useLanguage, useT } from './i18n'

const files = import.meta.glob<Record<string, string>>(['./locales/*.json', '../features/**/locales/*.json'], { eager: true, import: 'default' })

const keys = (messages: Record<string, string>) =>
  [...new Set(Object.keys(messages).map((k) => k.replace(/_(zero|one|two|few|many|other)$/, '')))].sort()

const arabicFiles = Object.keys(files).filter((path) => /(^|[/.])ar\.json$/.test(path))

describe('translations', () => {
  it.each(arabicFiles)('%s has the same keys in English', (path) => {
    const english = path.replace(/ar\.json$/, 'en.json')
    expect(keys(files[path])).toEqual(keys(files[english]))
  })
})

describe('useT', () => {
  const wrapper = ({ children }: { children: ReactNode }) => <LanguageProvider>{children}</LanguageProvider>
  const messages = {
    ar: { hello: 'أهلا {{name}}', files: '{{n}} ملف' },
    en: { hello: 'Hello {{name}}', files_one: '{{n}} file', files_other: '{{n}} files', onlyEn: 'English' },
  }

  function setup() {
    return renderHook(() => ({ t: useT(messages), language: useLanguage() }), { wrapper })
  }

  it('fills placeholders', () => {
    const { result } = setup()
    expect(result.current.t('hello', { name: 'Sara' })).toBe('أهلا Sara')
  })

  it('falls back to English, then the default value, then the key', () => {
    const { result } = setup()
    expect(result.current.t('onlyEn')).toBe('English')
    expect(result.current.t('missing', { defaultValue: 'CODE' })).toBe('CODE')
    expect(result.current.t('missing')).toBe('missing')
  })

  it('picks the plural form in English and the single form in Arabic', () => {
    const { result } = setup()
    expect(result.current.t('files', { count: 3, n: 3 })).toBe('3 ملف')

    act(() => result.current.language.setLang('en'))
    expect(result.current.t('files', { count: 1, n: 1 })).toBe('1 file')
    expect(result.current.t('files', { count: 3, n: 3 })).toBe('3 files')
  })

  it('switches the page direction with the language', () => {
    const { result } = setup()
    expect(document.documentElement.dir).toBe('rtl')

    act(() => result.current.language.setLang('en'))
    expect(document.documentElement.dir).toBe('ltr')
    expect(document.documentElement.lang).toBe('en')
  })
})
