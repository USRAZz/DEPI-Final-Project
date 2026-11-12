import type { ReactElement } from "react";

export type Lang = "ar" | "en";

/** Every feature folder exports `routes: FeatureRoute[]` from its routes.tsx. */
export type FeatureRoute = {
  path: string;
  label: Record<Lang, string>;
  element: ReactElement;
  roles?: string[];
  /** Sidebar link for a path with parameters. Without it, such a route stays out of the sidebar. */
  navTo?: string;
  /** Sidebar position, lowest first. Routes without one come last. */
  order?: number;
};
