import { env } from "@/lib/env";
import { type ChartMeta, type ChartResponse, type KpiResponse, sandboxLoader } from "@/lib/sandbox";

import type { ByTerm } from "../enrollment-trends/data";

/** /sandbox/executive-view: the cohort lenses and the payloads the page shows. */
export const cohortLenses = ["all", "2021-22", "2022-23", "2023-24", "2024-25"] as const;
export type CohortLens = (typeof cohortLenses)[number];

/** The years the "all" lens pools: the published results' pooled cohort, so 2024-25 is not in it. */
export const cohortPoolYears = ["2021-22", "2022-23", "2023-24"] as const;

export const cohortLensLabels: Record<CohortLens, string> = {
  all: `${cohortPoolYears[0]} to ${cohortPoolYears[cohortPoolYears.length - 1]}`,
  "2021-22": "2021-22",
  "2022-23": "2022-23",
  "2023-24": "2023-24",
  "2024-25": "2024-25",
};

export const DEFAULT_COHORT_LENS: CohortLens = "2024-25";

export type GapRow = {
  measure: string;
  group: string;
  rate: number;
  gap_pts: number;
  n: number;
  students_behind: number;
  by_cohort: { cohort: string; students_behind: number }[] | null;
};
export type Gaps = ChartResponse<GapRow>;

/** Loads the headcount lines, counting only the students who match the filters. */
export function headcountLoader(filters: CourseLoadFilters) {
  return sandboxLoader<ByTerm>(`/executive-view/headcount?${filterParams(filters)}`);
}

/** Loads the headline KPIs for one cohort lens, for the students who match the filters. */
export function kpisLoader(cohort: CohortLens, filters: CourseLoadFilters) {
  const params = filterParams(filters);
  params.set("cohort", cohort);
  return sandboxLoader<KpiResponse>(`/executive-view/kpis?${params}`);
}

/** One home state's matching students; n and share are null when hidden (under 10, or covering a smaller state). */
export type HomeStateRow = { state: string; n: number | null; share: number | null };

/** Loads headcount by home state for one cohort lens, for the students who match the filters. */
export function homeStatesLoader(cohort: CohortLens, filters: CourseLoadFilters) {
  const params = filterParams(filters);
  params.set("cohort", cohort);
  return sandboxLoader<ChartResponse<HomeStateRow>>(`/executive-view/home-states?${params}`);
}

/** One student's uploaded values, and the term they belong to for a per-term file. */
export type SupplementalRow = {
  student_id: string;
  academic_year: string | null;
  academic_term: string | null;
  values: Record<string, string | null>;
};
/** One uploaded file, back in its own shape. At most 500 rows are sent; total_rows says how many match. */
export type SupplementalFile = {
  file: string;
  uploaded_on: string | null;
  /** The upload's short id; null for an older upload. */
  upload_id: string | null;
  per_term: boolean;
  columns: string[];
  students: number;
  total_rows: number;
  rows: SupplementalRow[];
};
export type Supplemental = { meta: ChartMeta; files: SupplementalFile[] };

/** Loads the uploaded supplemental files for one cohort lens, for the students who match the filters. */
export function supplementalLoader(cohort: CohortLens, filters: CourseLoadFilters) {
  const params = filterParams(filters);
  params.set("cohort", cohort);
  return sandboxLoader<Supplemental>(`/executive-view/supplemental?${params}`);
}

/** The headline measures whose student IDs can be exported, as the API names them. */
export const exportMeasures = ["retention", "persistence", "gateway_math", "gateway_english", "graduation"] as const;
export type ExportMeasure = (typeof exportMeasures)[number];

/** Where to download the student IDs behind the headline measures: all of them, or one. */
export function studentExportUrl(cohort: CohortLens, filters: CourseLoadFilters, measure?: ExportMeasure): string {
  const params = filterParams(filters);
  params.set("cohort", cohort);
  if (measure) params.set("measure", measure);
  return `${env.apiBaseUrl}/sandbox/executive-view/kpis/students.csv?${params}`;
}

/** Loads the largest equity gaps for one cohort lens. */
export function gapsLoader(cohort: CohortLens) {
  return sandboxLoader<Gaps>(`/executive-view/gaps?cohort=${cohort}`);
}

/** The course load filters, in menu order, as the API names them. "all" leaves one off. */
export const courseLoadFilterNames = ["goal", "program", "race", "gender", "age", "pell", "first_gen", "affinity"] as const;
export type CourseLoadFilterName = (typeof courseLoadFilterNames)[number];
export type CourseLoadFilters = Record<CourseLoadFilterName, string>;

export const NO_FILTERS: CourseLoadFilters = {
  goal: "all",
  program: "all",
  race: "all",
  gender: "all",
  age: "all",
  pell: "all",
  first_gen: "all",
  affinity: "all",
};

/** True when any filter is on. */
export function isFiltered(filters: CourseLoadFilters): boolean {
  return courseLoadFilterNames.some((name) => filters[name] !== "all");
}

/** Query parameters for only the filters that are on. */
export function filterParams(filters: CourseLoadFilters): URLSearchParams {
  const params = new URLSearchParams();
  for (const name of courseLoadFilterNames) {
    if (filters[name] !== "all") params.set(name, filters[name]);
  }
  return params;
}

type FilterMenu = { label: string; values: readonly string[]; labels: Record<string, string> };

/** The fixed filters' menus. Program's menu comes from the API, since programs vary by cohort. */
export const courseLoadFilterMenus: Record<Exclude<CourseLoadFilterName, "program">, FilterMenu> = {
  goal: {
    label: "Goal",
    values: ["all", "associate", "certificate", "other"],
    labels: {
      all: "All goals",
      associate: "Associate-seekers",
      certificate: "Certificate-seekers",
      other: "Other or unknown goal",
    },
  },
  race: {
    label: "Race",
    values: [
      "all",
      "white",
      "hispanic",
      "black",
      "asian",
      "two_or_more",
      "nonresident",
      "american_indian",
      "pacific_islander",
      "unknown",
    ],
    labels: {
      all: "All races",
      white: "White",
      hispanic: "Hispanic",
      black: "Black or African American",
      asian: "Asian",
      two_or_more: "Two or More Races",
      nonresident: "Nonresident alien",
      american_indian: "American Indian or Alaska Native",
      pacific_islander: "Native Hawaiian or Other Pacific Islander",
      unknown: "Unknown",
    },
  },
  gender: {
    label: "Gender",
    values: ["all", "female", "male", "x", "unknown"],
    labels: { all: "All genders", female: "Female", male: "Male", x: "Gender X", unknown: "Unknown" },
  },
  age: {
    label: "Age",
    values: ["all", "20_and_younger", "over_20_to_24", "over_24", "unknown"],
    labels: {
      all: "All ages",
      "20_and_younger": "20 and younger",
      over_20_to_24: "Over 20, up to 24",
      over_24: "Over 24",
      unknown: "Unknown",
    },
  },
  pell: {
    label: "Pell",
    values: ["all", "yes", "no", "unknown"],
    labels: { all: "Pell or not", yes: "Pell", no: "No Pell", unknown: "Unknown" },
  },
  first_gen: {
    label: "First generation",
    values: ["all", "yes", "no", "not_reported"],
    labels: { all: "Any", yes: "First generation", no: "Not first generation", not_reported: "Not reported" },
  },
  affinity: {
    label: "Affinity group",
    values: [
      "all",
      "none",
      "band",
      "choir",
      "theater",
      "football",
      "baseball",
      "basketball",
      "volleyball",
      "soccer",
      "student_government",
      "esports",
    ],
    labels: {
      all: "All groups",
      none: "No group",
      band: "Band",
      choir: "Choir",
      theater: "Theater",
      football: "Football",
      baseball: "Baseball",
      basketball: "Basketball",
      volleyball: "Volleyball",
      soccer: "Soccer",
      student_government: "Student Government",
      esports: "Esports",
    },
  },
};

/** How many credits each band of the curve holds. A display setting, so Clear filters keeps it. */
export const granularities = ["1", "3", "6"] as const;
export type Granularity = (typeof granularities)[number];
export const DEFAULT_GRANULARITY: Granularity = "3";
export const granularityLabels: Record<Granularity, string> = {
  "1": "Every credit",
  "3": "Bands of 3 credits",
  "6": "Bands of 6 credits",
};

/** One group's share of students in each credits band. Everything is null for a hidden group. */
export type LoadCurve = {
  group: string;
  n: number | null;
  median_credits: number | null;
  under_12_pct: number | null;
  on_track_pct: number | null;
  shares: (number | null)[];
};

export type CourseLoad = {
  meta: ChartMeta;
  bands: string[];
  on_track_band: string;
  everyone: LoadCurve;
  /** Null when no filter is on. */
  selected: LoadCurve | null;
  hidden_reason: string | null;
};

export type ProgramOption = { code: string; label: string };

/** Loads the year-1 course load for one cohort lens and band size, with only the filters that are on. */
export function courseLoadLoader(cohort: CohortLens, filters: CourseLoadFilters, granularity: Granularity) {
  const params = filterParams(filters);
  params.set("cohort", cohort);
  params.set("granularity", granularity);
  return sandboxLoader<CourseLoad>(`/executive-view/course-load?${params}`);
}

/** Loads the programs the program filter offers in one cohort lens. */
export function courseLoadProgramsLoader(cohort: CohortLens) {
  return sandboxLoader<ProgramOption[]>(`/executive-view/course-load/programs?cohort=${cohort}`);
}
