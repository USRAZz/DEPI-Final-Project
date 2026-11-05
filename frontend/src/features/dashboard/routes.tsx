import type { FeatureRoute } from "../../app/types";
import { DashboardPage } from "./DashboardPage";

export const routes: FeatureRoute[] = [{ path: "/", label: { ar: "لوحة التحكم", en: "Dashboard" }, order: 0, element: <DashboardPage /> }];
