import { type SearchParams, parseChoice } from "@/lib/routes";
import { type ChartResponse, sandboxLoader } from "@/lib/sandbox";

/** /sandbox/aid-momentum: the measure filter and the three payloads the page charts. */
export const measures = [
  "retention",
  "persistence",
  "gateway_math",
  "gateway_english",
  "dfw_rate",
  "credit_completion",
] as const;
export type Measure = (typeof measures)[number];

export const measureLabels: Record<Measure, string> = {
  retention: "Retention",
  persistence: "Persistence elsewhere",
  gateway_math: "Gateway math, year 1",
  gateway_english: "Gateway English, year 1",
  dfw_rate: "DFW rate",
  credit_completion: "Credit completion",
};

/** The measure the picker starts on from a link's measure param; an unknown value falls back to retention. */
export function measureFromParams(params: SearchParams): Measure {
  return parseChoice(params.measure, measures, "retention");
}

/** A higher rate is worse for these, so the page words the reading the other way round. */
export const lowerIsBetter: ReadonlySet<Measure> = new Set<Measure>(["dfw_rate"]);

export type BandRow = { band: string; rate: number | null; n: number | null; is_everyone: boolean };
export type Bands = ChartResponse<BandRow>;

export type BandGapRow = {
  band: string;
  gap_pts: number;
  ci_low: number;
  ci_high: number;
  q_value: number;
  likely_noise: boolean;
  rank: number;
  ranked_of: number;
};
export type BandGaps = ChartResponse<BandGapRow>;

export type PellRow = {
  group: string;
  rate: number | null;
  n: number | null;
  series: "pell" | "unmet_need_band";
  is_real: boolean;
};
export type Pell = ChartResponse<PellRow>;

/** Loads one measure by unmet need band. */
export function bandsLoader(measure: Measure) {
  return sandboxLoader<Bands>(`/aid-momentum/bands?measure=${measure}`);
}

/** Loads the gap finder's ranked band gaps for one measure. */
export function gapsLoader(measure: Measure) {
  return sandboxLoader<BandGaps>(`/aid-momentum/gaps?measure=${measure}`);
}

/** Loads Pell status beside the unmet need bands for one measure. */
export function pellLoader(measure: Measure) {
  return sandboxLoader<Pell>(`/aid-momentum/pell?measure=${measure}`);
}
