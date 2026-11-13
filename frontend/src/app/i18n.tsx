import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import ar from "./locales/ar.json";
import en from "./locales/en.json";
import type { Lang } from "./types";

type Messages = Record<string, string>;
type Vars = Record<string, string | number | undefined>;
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
 * Optional vars fill {{placeholders}}: t("hello", { name }). A numeric `count` picks
 * key_one / key_other when those exist, and `defaultValue` replaces a missing key.
 * A missing key falls back to English, then to the key itself.
 */
export function useT(messages: Record<Lang, Messages>) {
  const { lang } = useLanguage();
  return useCallback(
    (key: string, vars?: Vars) => {
      const count = vars?.count;
      const keys = typeof count === "number" ? [`${key}_${new Intl.PluralRules(lang).select(count)}`, `${key}_other`, key] : [key];
      const find = (table: Messages) => keys.map((k) => table[k]).find((text) => text !== undefined);
      const text = find(messages[lang]) ?? find(messages.en) ?? vars?.defaultValue ?? key;
      return String(text).replace(/\{\{(\w+)\}\}/g, (match, name: string) => String(vars?.[name] ?? match));
    },
    [lang, messages],
  );
}

const shell = { ar, en };

/** Terms shared across the app: roles, banks, risk levels, loading and error text. */
export function useShellT() {
  return useT(shell);
}

const LOCALE: Record<Lang, string> = { ar: "ar-EG", en: "en-EG" };

/** Amounts are stored as numbers; only their display changes with the language. */
export function formatMoney(amount: number, lang: Lang, currency = "EGP") {
  return new Intl.NumberFormat(LOCALE[lang], { style: "currency", currency }).format(amount);
}

export function formatDate(iso: string, lang: Lang) {
  return new Intl.DateTimeFormat(LOCALE[lang], { dateStyle: "medium" }).format(new Date(iso));
}
