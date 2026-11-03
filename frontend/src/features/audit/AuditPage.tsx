// Owner: Anan
import { useT } from "../../app/i18n";
import ar from "./locales/ar.json";
import en from "./locales/en.json";

const messages = { ar, en };

export function AuditPage() {
  const t = useT(messages);
  return (
    <section>
      <h2>{t("title")}</h2>
      <p>{t("empty")}</p>
    </section>
  );
}
