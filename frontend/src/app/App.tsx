import { BrowserRouter, Route, Routes } from "react-router-dom";
import { LanguageProvider } from "./i18n";
import { Layout } from "./Layout";
import { NotFound } from "./placeholders";
import type { FeatureRoute } from "./types";

// Auto-discovers every features/*/routes.tsx, so nobody edits a central routes file.
const modules = import.meta.glob<{ routes: FeatureRoute[] }>("../features/*/routes.tsx", { eager: true });
const routes: FeatureRoute[] = Object.values(modules).flatMap((m) => m.routes);

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout routes={routes} />}>
        {routes.map((r) => (
          <Route key={r.path} path={r.path} element={r.element} />
        ))}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <LanguageProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </LanguageProvider>
  );
}
