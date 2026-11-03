import type { FeatureRoute } from "../../app/types";
import { LoginPage } from "./LoginPage";

export const routes: FeatureRoute[] = [{ path: "/login", label: { ar: "تسجيل الدخول", en: "Sign in" }, element: <LoginPage /> }];
