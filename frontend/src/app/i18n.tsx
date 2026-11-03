import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Lang } from "./types";

type Messages = Record<string, string>;
type Ctx = { lang: Lang; setLang: (l: Lang) => void };

const LanguageContext = createContext<Ctx>({ lang: "ar", setLang: () => {} });
const STORAGE_KEY = "securefin.lang";

function readStoredLang(): Lang {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "en" ? "en" : "ar";
  } catch {
    return "ar";
  }
}

/** Arabic is the default. Switching language flips the whole page to right-to-left. */
export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readStoredLang);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* storage blocked: keep the choice for this session only */
    }
  }, []);

  const value = useMemo(() => ({ lang, setLang }), [lang, setLang]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  return useContext(LanguageContext);
}

/**
 * Each feature passes its own message files, so translations never collide:
 *   const t = useT({ ar, en });  t("title")
 * A missing key falls back to English, then to the key itself.
 */
export function useT(messages: Record<Lang, Messages>) {
  const { lang } = useLanguage();
  return useCallback((key: string) => messages[lang][key] ?? messages.en[key] ?? key, [lang, messages]);
}

const LOCALE: Record<Lang, string> = { ar: "ar-EG", en: "en-EG" };

/** Amounts are stored as numbers; only their display changes with the language. */
export function formatMoney(amount: number, lang: Lang, currency = "EGP") {
  return new Intl.NumberFormat(LOCALE[lang], { style: "currency", currency }).format(amount);
}

export function formatDate(iso: string, lang: Lang) {
  return new Intl.DateTimeFormat(LOCALE[lang], { dateStyle: "medium" }).format(new Date(iso));
}
