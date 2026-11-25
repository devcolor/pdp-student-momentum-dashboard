import { type ChartResponse, sandboxLoader } from "@/lib/sandbox";

/** One metric for one entering cohort. value, numerator and n are null when suppressed. */
export type TrendRow = {
  metric: string;
  label: string;
  unit: "count" | "percent";
  cohort: string;
  value: number | null;
  numerator: number | null;
  n: number | null;
  /** True when the cohort hasn't had the metric's full window yet. */
  partial: boolean;
};
export type Trends = ChartResponse<TrendRow>;

/** Loads all five metrics for every entering cohort. */
export const trendsLoader = sandboxLoader<Trends>("/student-success/trends");
