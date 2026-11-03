import type { FeatureRoute } from "../../app/types";
import { SecurityPage } from "./SecurityPage";

export const routes: FeatureRoute[] = [{ path: "/security", label: { ar: "لوحة الأمان", en: "Security" }, element: <SecurityPage /> }];
