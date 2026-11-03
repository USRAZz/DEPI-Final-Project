import type { FeatureRoute } from "../../app/types";
import { ReportsPage } from "./ReportsPage";

export const routes: FeatureRoute[] = [{ path: "/reports", label: { ar: "التقارير", en: "Reports" }, element: <ReportsPage /> }];
