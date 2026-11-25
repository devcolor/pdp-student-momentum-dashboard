import { type ChartResponse, type KpiResponse, sandboxLoader } from "@/lib/sandbox";

/** /sandbox/enrollment-trends: typed filters and the payloads the page charts. */
export const splitBys = ["enrollment_type", "enrollment_intensity", "pell", "entry_term"] as const;
export type SplitBy = (typeof splitBys)[number];

export const splitByLabels: Record<SplitBy, string> = {
  enrollment_type: "Enrollment type",
  enrollment_intensity: "First-term intensity",
  pell: "Pell status, first year",
  entry_term: "Entry term",
};

export type EnteringRow = {
  cohort: string;
  group: string;
  n: number | null;
  share: number | null;
  cohort_total: number;
};
export type Entering = ChartResponse<EnteringRow>;

export type TermRow = { term: string; cohort: string; n: number | null; term_total: number };
export type ByTerm = ChartResponse<TermRow>;

/** Loads entering students per cohort, split by one student group. */
export function enteringLoader(splitBy: SplitBy) {
  return sandboxLoader<Entering>(`/enrollment-trends/entering?split_by=${splitBy}`);
}

export const byTermLoader = sandboxLoader<ByTerm>("/enrollment-trends/by-term");

export const kpisLoader = sandboxLoader<KpiResponse>("/enrollment-trends/kpis");

export const KPI_COUNT = 4;
