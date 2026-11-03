import type { ReactElement } from "react";

export type Lang = "ar" | "en";

/** Every feature folder exports `routes: FeatureRoute[]` from its routes.tsx. */
export type FeatureRoute = {
  path: string;
  label: Record<Lang, string>;
  element: ReactElement;
  roles?: string[];
};
