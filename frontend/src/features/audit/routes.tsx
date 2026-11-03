import type { FeatureRoute } from "../../app/types";
import { AuditPage } from "./AuditPage";

export const routes: FeatureRoute[] = [{ path: "/audit", label: { ar: "سجل المراجعة", en: "Audit log" }, element: <AuditPage /> }];
