import type { FeatureRoute } from "../../app/types";
import { AgentPage } from "./AgentPage";

export const routes: FeatureRoute[] = [{ path: "/assistant", label: { ar: "المساعد", en: "Assistant" }, element: <AgentPage /> }];
