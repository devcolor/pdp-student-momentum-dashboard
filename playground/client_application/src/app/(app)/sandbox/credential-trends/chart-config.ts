/** /sandbox/credential-trends: turn the server's long rows into chart rows, bars and table rows. */

import { type BarListItem, type ChartSeries, formatCount } from "@/lib/charts";

import type { CohortRateRow, DriverRow, PathwayRow, ProgramRow } from "./data";

export const SUPPRESSED_LABEL = "<10";

export type ValuesTable = { columns: string[]; rows: { label: string; cells: string[] }[] };

type Pivot = { chartRows: Record<string, string | number>[]; series: ChartSeries[] };

/** Distinct values, in the order they first appear. */
function distinct(values: string[]): string[] {
  return [...new Set(values)];
}

/** Pivot long rows into one chart row per category, with one positional key per part. */
function pivot<Row>(
  rows: Row[],
  categoryKey: string,
  categoryOf: (row: Row) => string,
  partOf: (row: Row) => string,
  valueOf: (row: Row) => number | null,
): Pivot {
  const parts = distinct(rows.map(partOf));
  // Labels can hold spaces and punctuation, so the chart keys are positional.
  const keyOf = (part: string) => `part_${parts.indexOf(part)}`;
  const chartRows = distinct(rows.map(categoryOf)).map((category) => {
    const chartRow: Record<string, string | number> = { [categoryKey]: category };
    for (const row of rows.filter((each) => categoryOf(each) === category)) {
      const value = valueOf(row);
      if (value !== null) chartRow[keyOf(partOf(row))] = value;
    }
    return chartRow;
  });
  return { chartRows, series: parts.map((part) => ({ key: keyOf(part), label: part })) };
}

/** A scale top a little above the largest value, rounded up to a step, so labels fit over the bars. */
export function scaleTop(values: (number | null)[], step: number): number {
  const largest = Math.max(0, ...values.filter((value): value is number => value !== null));
  return Math.max(step, Math.ceil((largest * 1.15) / step) * step);
}

/** The axis name for a cohort: its year and the full years it has had. */
export function cohortLabel(row: CohortRateRow): string {
  if (row.status === "too_new") return `${row.cohort} · too new`;
  if (row.full_years_seen === null) return row.cohort;
  // The data model counts at most 4 years, so 3 full years can mean 3 or more.
  if (row.full_years_seen >= 3) return `${row.cohort} · 3+ yrs`;
  return `${row.cohort} · ${row.full_years_seen} yr${row.full_years_seen === 1 ? "" : "s"}`;
}

/** Associate and certificate rates side by side, one pair of bars per cohort. */
export function cohortRateChart(rows: CohortRateRow[]): Pivot & { max: number } {
  const chart = pivot(rows, "cohort", cohortLabel, (row) => row.credential, (row) => row.rate);
  return { ...chart, max: scaleTop(rows.map((row) => row.rate), 5) };
}

/** One cohort's rate and counts, or why it isn't shown. */
function rateCell(row: CohortRateRow | undefined): string {
  if (!row) return "";
  if (row.status === "too_new") return "Too new";
  if (row.rate === null || row.n === null || row.earned === null) return SUPPRESSED_LABEL;
  return `${row.rate}% · ${formatCount(row.earned)} of ${formatCount(row.n)}`;
}

/** One cohort's 95% interval, or blank when the rate isn't shown. */
function intervalCell(row: CohortRateRow | undefined): string {
  if (!row || row.ci_low === null || row.ci_high === null) return "";
  return `${row.ci_low} to ${row.ci_high}`;
}

/** The exact rates behind the cohort chart: each credential's rate and counts, then its interval. */
export function cohortRateTable(rows: CohortRateRow[]): ValuesTable {
  const cohorts = distinct(rows.map((row) => row.cohort));
  const credentials = distinct(rows.map((row) => row.credential));
  const find = (cohort: string, credential: string) =>
    rows.find((row) => row.cohort === cohort && row.credential === credential);
  return {
    columns: cohorts,
    rows: credentials.flatMap((credential) => [
      { label: credential, cells: cohorts.map((cohort) => rateCell(find(cohort, credential))) },
      // Labels key the table rows, so each interval row names its credential.
      { label: `${credential.split(" ")[0]} 95% interval`, cells: cohorts.map((cohort) => intervalCell(find(cohort, credential))) },
    ]),
  };
}

/** Earners per cohort, stacked by program. */
export function programChart(rows: ProgramRow[]): Pivot & { max: number } {
  const chart = pivot(rows, "cohort", (row) => row.cohort, (row) => row.program, (row) => row.earned);
  const shownTotals = chart.chartRows.map((chartRow) =>
    chart.series.reduce((total, part) => total + Number(chartRow[part.key] ?? 0), 0),
  );
  return { ...chart, max: scaleTop(shownTotals, 50) };
}

/** The exact counts behind the program chart, one row per program and a total line. */
export function programTable(rows: ProgramRow[]): ValuesTable {
  const cohorts = distinct(rows.map((row) => row.cohort));
  const programs = distinct(rows.map((row) => row.program));
  const count = (value: number | null) => (value === null ? SUPPRESSED_LABEL : formatCount(value));
  return {
    columns: cohorts,
    rows: [
      ...programs.map((program) => ({
        label: program,
        cells: cohorts.map((cohort) => {
          const match = rows.find((row) => row.cohort === cohort && row.program === program);
          return match ? count(match.earned) : "";
        }),
      })),
      {
        label: "Total",
        cells: cohorts.map((cohort) => count(rows.find((row) => row.cohort === cohort)?.cohort_earned ?? null)),
      },
    ],
  };
}

/** Each pathway's share of one goal's earners, stacked to 100. */
export function pathwayChart(rows: PathwayRow[]): Pivot {
  return pivot(rows, "sought", (row) => row.sought, (row) => row.pathway, (row) => row.share);
}

/** The exact counts and shares behind the pathway chart, with each goal's total. */
export function pathwayTable(rows: PathwayRow[]): ValuesTable {
  const goals = distinct(rows.map((row) => row.sought));
  const pathways = distinct(rows.map((row) => row.pathway));
  return {
    columns: goals,
    rows: [
      ...pathways.map((pathway) => ({
        label: pathway,
        cells: goals.map((goal) => {
          const match = rows.find((row) => row.sought === goal && row.pathway === pathway);
          if (!match) return "";
          return match.n === null ? SUPPRESSED_LABEL : `${formatCount(match.n)} · ${match.share}%`;
        }),
      })),
      {
        label: "Total",
        cells: goals.map((goal) => {
          const total = rows.find((row) => row.sought === goal)?.sought_total ?? null;
          return total === null ? SUPPRESSED_LABEL : formatCount(total);
        }),
      },
    ],
  };
}

/** A signed gap in points, to one decimal, e.g. "+17.9 pts". */
function formatGap(gap: number): string {
  const rounded = Math.round(gap * 10) / 10;
  return `${rounded > 0 ? "+" : ""}${rounded} pts`;
}

/** One bar per group: its rate, its gap from everyone else, and a caution when the gap may be chance. */
export function driverBars(rows: DriverRow[]): BarListItem[] {
  return rows.map((row) => {
    if (row.rate === null || row.n === null) {
      return { label: row.group, value: null, display: SUPPRESSED_LABEL, note: "too few students" };
    }
    const students = `${formatCount(row.n)} students`;
    if (row.status === "unknown_group" || row.gap_pts === null) {
      return { label: row.group, value: row.rate, display: `${row.rate}%`, note: `${students} · not compared` };
    }
    const caution = row.likely_noise ? " · likely noise" : "";
    return {
      label: row.group,
      value: row.rate,
      display: `${row.rate}% · ${formatGap(row.gap_pts)}`,
      note: `${students}${caution}`,
    };
  });
}
