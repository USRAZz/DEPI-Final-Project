import type { FeatureRoute } from "../../app/types";
import { ApprovalsPage } from "./ApprovalsPage";

export const routes: FeatureRoute[] = [{ path: "/approvals", label: { ar: "الموافقات", en: "Approvals" }, element: <ApprovalsPage /> }];
