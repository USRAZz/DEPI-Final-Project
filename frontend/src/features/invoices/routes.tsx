import type { FeatureRoute } from "../../app/types";
import { InvoiceReviewPage } from "./InvoiceReviewPage";
import { InvoicesPage } from "./InvoicesPage";

export const routes: FeatureRoute[] = [
  { path: "/invoices", label: { ar: "الفواتير", en: "Invoices" }, element: <InvoicesPage />, order: 1 },
  { path: "/invoices/:invoiceId", label: { ar: "مراجعة فاتورة", en: "Invoice review" }, element: <InvoiceReviewPage /> },
];
