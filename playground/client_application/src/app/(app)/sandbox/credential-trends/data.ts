import { type ChartResponse, sandboxLoader } from "@/lib/sandbox";

/** /sandbox/credential-trends: typed filters and the payloads the page charts. */
export const windows = ["so_far", "1", "2", "3"] as const;
export type Window = (typeof windows)[number];

export const fixedWindows = ["1", "2", "3"] as const;
export type FixedWindow = (typeof fixedWindows)[number];

export const windowLabels: Record<Window, string> = {
  so_far: "So far",
  "1": "Within 1 year",
  "2": "Within 2 years",
  "3": "Within 3 years",
};

export const credentials = ["certificate", "associate"] as const;
export type Credential = (typeof credentials)[number];

export const credentialLabels: Record<Credential, string> = {
  certificate: "Certificate",
  associate: "Associate degree",
};

export const factors = [
  "gateway_math",
  "gateway_english",
  "enrollment_intensity",
  "enrollment_type",
  "pell",
  "age",
  "entry_term",
] as const;
export type Factor = (typeof factors)[number];

export const factorLabels: Record<Factor, string> = {
  gateway_math: "Gateway math in year 1",
  gateway_english: "Gateway English in year 1",
  enrollment_intensity: "First-term intensity",
  enrollment_type: "Enrollment type",
  pell: "Pell status, first year",
  age: "Age at entry",
  entry_term: "Entry term",
};

export type CohortRateRow = {
  cohort: string;
  full_years_seen: number | null;
  credential: string;
  status: "ok" | "too_new" | "suppressed";
  earned: number | null;
  n: number | null;
  rate: number | null;
  ci_low: number | null;
  ci_high: number | null;
};
export type ByCohort = ChartResponse<CohortRateRow>;

export type ProgramRow = { cohort: string; program: string; earned: number | null; cohort_earned: number | null };
export type ByProgram = ChartResponse<ProgramRow>;

export type DriverRow = {
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
export type Drivers = ChartResponse<DriverRow> & { everyone_rate: number | null };

export type PathwayRow = {
  sought: string;
  pathway: string;
  n: number | null;
  share: number | null;
  sought_total: number | null;
};
export type Pathways = ChartResponse<PathwayRow>;

/** Loads both credentials' rates per cohort, counted so far or within a fixed number of years. */
export function byCohortLoader(window: Window) {
  return sandboxLoader<ByCohort>(`/credential-trends/by-cohort?window=${window}`);
}

/** Loads earners per cohort, split by program. */
export function byProgramLoader(credential: Credential, window: FixedWindow) {
  return sandboxLoader<ByProgram>(`/credential-trends/by-program?credential=${credential}&window=${window}`);
}

/** Loads each group's completion rate against everyone else who came for the credential. */
export function driversLoader(credential: Credential, window: FixedWindow, factor: Factor) {
  return sandboxLoader<Drivers>(
    `/credential-trends/drivers?credential=${credential}&window=${window}&factor=${factor}`,
  );
}

/** Loads associate only, certificate only, or both, by what students came for. */
export function pathwaysLoader(window: FixedWindow) {
  return sandboxLoader<Pathways>(`/credential-trends/pathways?window=${window}`);
}
