import type { FeatureRoute } from "../../app/types";
import { PaymentApprovalPage } from "./PaymentApprovalPage";

export const routes: FeatureRoute[] = [{ path: "/payments/:requestId", navTo: "/payments/187", label: { ar: "المدفوعات", en: "Payments" }, order: 2, element: <PaymentApprovalPage /> }];
