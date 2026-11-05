import type { FeatureRoute } from "../../app/types";
import { BankChangePage } from "./BankChangePage";

export const routes: FeatureRoute[] = [{ path: "/vendors/:vendorId/bank-change", navTo: "/vendors/2/bank-change", label: { ar: "الموردين", en: "Vendors" }, order: 3, element: <BankChangePage /> }];
