import { type ChartResponse, sandboxLoader } from "@/lib/sandbox";

/** /sandbox/associate-momentum: typed filters and the payloads the page charts. */
export const windows = ["2", "3"] as const;
export type Window = (typeof windows)[number];

export const windowLabels: Record<Window, string> = {
  "2": "Within 2 years",
  "3": "Within 3 years",
};

export const splits = ["credits_short", "enrollment", "intensity"] as const;
export type Split = (typeof splits)[number];

export const splitLabels: Record<Split, string> = {
  credits_short: "Credits short",
  enrollment: "Enrolled after",
  intensity: "First-term intensity",
};

export type MilestoneRow = {
  cohort: string;
  milestone: string;
  status: "ok" | "suppressed";
  reached: number | null;
  n: number | null;
  rate: number | null;
};
export type Milestones = ChartResponse<MilestoneRow>;

export type NearCompleterRow = {
  cohort: string;
  part: string;
  count: number | null;
  share_of_pool: number | null;
  pool: number | null;
  seekers: number | null;
  pool_rate: number | null;
};
export type NearCompleters = ChartResponse<NearCompleterRow>;

export type MomentumRow = {
  group: string;
  status: "ok" | "suppressed" | "unknown_group";
  earned: number | null;
  n: number | null;
  rate: number | null;
  comparison_rate: number | null;
  gap_pts: number | null;
  ci_low: number | null;
  ci_high: number | null;
  likely_noise: boolean | null;
};
export type YearOne = ChartResponse<MomentumRow> & { everyone_rate: number | null };

/** Loads the share of associate-seekers reaching each credit milestone, per cohort. */
export function milestonesLoader(window: Window) {
  return sandboxLoader<Milestones>(`/associate-momentum/milestones?window=${window}`);
}

/** Loads near-completers per cohort, split one way. */
export function nearCompletersLoader(window: Window, split: Split) {
  return sandboxLoader<NearCompleters>(`/associate-momentum/near-completers?window=${window}&split=${split}`);
}

/** Loads the associate rate for each year-1 credit band, against everyone else. */
export function yearOneLoader(window: Window) {
  return sandboxLoader<YearOne>(`/associate-momentum/year-one?window=${window}`);
}
