import { env } from "@/lib/env";
import { type SearchParams, parseChoice } from "@/lib/routes";
import { type ChartMeta, type KpiResponse, type KpiTrend, sandboxLoader } from "@/lib/sandbox";

import type { CohortLens } from "../executive-view/data";

/** Which university's version of the page: MVSU drops the associate tile and "Where to start". */
export type School = "ccac" | "mvsu";

/** Enrollment, retention, persistence, transfer and completion. */
export const SNAPSHOT_KPI_COUNT = 5;

/** Loads the snapshot's five KPIs for one cohort lens. */
export function snapshotKpisLoader(cohort: CohortLens) {
  return sandboxLoader<KpiResponse>(`/student-success/kpis?cohort=${cohort}`);
}

/** The equity dimensions the analysis card splits by, as the API names them. */
export const equityDimensions = ["race", "gender", "age_band", "first_gen", "pell"] as const;
export type EquityDimension = (typeof equityDimensions)[number];

/** The dimension the split-by picker starts on from a link's dimension param; an unknown value falls back to race. */
export function dimensionFromParams(params: SearchParams): EquityDimension {
  return parseChoice(params.dimension, equityDimensions, "race");
}

export const equityDimensionLabels: Record<EquityDimension, string> = {
  race: "Race/ethnicity",
  gender: "Gender",
  age_band: "Age group",
  first_gen: "First generation",
  pell: "Pell status",
};

export const equityViews = ["population", "programs", "momentum"] as const;
export type EquityView = (typeof equityViews)[number];

export const equityViewLabels: Record<EquityView, string> = {
  population: "Student population",
  programs: "Academic programs",
  momentum: "Credit momentum",
};

/** One group's size, retention gap and credit milestones. Null means hidden. */
export type EquityGroup = {
  group: string;
  n: number | null;
  share: number | null;
  retention: number | null;
  retention_gap_pts: number | null;
  likely_noise: boolean | null;
  milestones: (number | null)[];
};

export type EquityProgram = {
  code: string;
  label: string;
  n: number;
  segments: { group: string; n: number | null }[];
};

export type EquityAnalysis = {
  meta: ChartMeta;
  milestones: string[];
  groups: EquityGroup[];
  everyone: EquityGroup;
  programs: EquityProgram[];
};

/** Loads all three views for one cohort lens and equity dimension. */
export function equityLoader(cohort: CohortLens, dimension: EquityDimension) {
  return sandboxLoader<EquityAnalysis>(`/student-success/equity?cohort=${cohort}&dimension=${dimension}`);
}

/** One action: how many students, what it means, and the suggested next step. */
export type ActionTile = {
  id: string;
  label: string;
  value: number | null;
  share: number | null;
  detail: string;
  action: string;
  /** Change in share from the prior cohort; null for the pooled cohorts. */
  trend: KpiTrend | null;
};

/** One equity group's count in each action. Null means hidden. */
export type ActionGroupRow = {
  group: string;
  n: number | null;
  stopped_out: number | null;
  near_15: number | null;
  gateway: number | null;
  priority: number | null;
};

export type GatewayCourseRow = { course: string; subject: string; dfw_rate: number; n: number };

export type ActionBoard = {
  meta: ChartMeta;
  tiles: ActionTile[];
  groups: ActionGroupRow[];
  gateway_courses: GatewayCourseRow[];
};

/** Where to download the student IDs behind the action board: every tile's flags, or one tile's students. */
export function actionStudentsUrl(cohort: CohortLens, school: School, tile?: string): string {
  const params = new URLSearchParams({ cohort, school });
  if (tile) params.set("tile", tile);
  return `${env.apiBaseUrl}/sandbox/student-success/actions/students.csv?${params}`;
}

/** Loads one school's action board for one cohort lens and equity dimension. */
export function actionsLoader(cohort: CohortLens, dimension: EquityDimension, school: School) {
  return sandboxLoader<ActionBoard>(`/student-success/actions?cohort=${cohort}&dimension=${dimension}&school=${school}`);
}
