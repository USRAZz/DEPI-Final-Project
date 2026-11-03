import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import ar from "./locales/ar.json";
import en from "./locales/en.json";
import { LanguageProvider, useLanguage, useT } from "./i18n";
import type { FeatureRoute } from "./types";

// Auto-discovers every features/*/routes.tsx, so nobody edits a central routes file.
const modules = import.meta.glob<{ routes: FeatureRoute[] }>("../features/*/routes.tsx", { eager: true });
const routes: FeatureRoute[] = Object.values(modules).flatMap((m) => m.routes);
const shell = { ar, en };

function Shell() {
  const { lang, setLang } = useLanguage();
  const t = useT(shell);
  return (
    <BrowserRouter>
      <nav style={{ display: "flex", gap: 16, padding: 12, borderBottom: "1px solid #ddd", alignItems: "center" }}>
        <strong>{t("appName")}</strong>
        {routes.map((r) => (
          <Link key={r.path} to={r.path}>
            {r.label[lang]}
          </Link>
        ))}
        <button style={{ marginInlineStart: "auto" }} onClick={() => setLang(lang === "ar" ? "en" : "ar")}>
          {t("switchLanguage")}
        </button>
      </nav>
      <main style={{ padding: 16 }}>
        <Routes>
          {routes.map((r) => (
            <Route key={r.path} path={r.path} element={r.element} />
          ))}
          <Route path="*" element={<p>{t("welcome")}</p>} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}

export function App() {
  return (
    <LanguageProvider>
      <Shell />
    </LanguageProvider>
  );
}
