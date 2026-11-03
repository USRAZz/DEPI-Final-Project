import type { FeatureRoute } from "../../app/types";
import { InvoicesPage } from "./InvoicesPage";

export const routes: FeatureRoute[] = [{ path: "/invoices", label: { ar: "الفواتير", en: "Invoices" }, element: <InvoicesPage /> }];
