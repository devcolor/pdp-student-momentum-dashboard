/** /sandbox/associate-momentum: turn the server's long rows into chart rows, bars and table rows. */

import { type BarListItem, type ChartSeries, formatCount } from "@/lib/charts";

import type { MilestoneRow, MomentumRow, NearCompleterRow } from "./data";

export const SUPPRESSED_LABEL = "<10";

export type ValuesTable = { columns: string[]; rows: { label: string; cells: string[] }[] };

type ChartRow = Record<string, string | number>;

/** Distinct values, in the order they first appear. */
function distinct(values: string[]): string[] {
  return [...new Set(values)];
}

/** The funnel for the oldest and newest cohort, one pair of bars per milestone; null with fewer than two. */
export function milestoneChart(rows: MilestoneRow[]): { chartRows: ChartRow[]; series: [ChartSeries, ChartSeries] } | null {
  const cohorts = distinct(rows.map((row) => row.cohort));
  if (cohorts.length < 2) return null;
  const oldest = cohorts[0];
  const newest = cohorts[cohorts.length - 1];
  const rateOf = (cohort: string, milestone: string) =>
    rows.find((row) => row.cohort === cohort && row.milestone === milestone)?.rate ?? null;

  const chartRows = distinct(rows.map((row) => row.milestone)).map((milestone) => {
    const chartRow: ChartRow = { milestone };
    const oldestRate = rateOf(oldest, milestone);
    const newestRate = rateOf(newest, milestone);
    // A hidden share is left out, so its bar is missing rather than drawn at zero.
    if (oldestRate !== null) chartRow.oldest = oldestRate;
    if (newestRate !== null) chartRow.newest = newestRate;
    return chartRow;
  });
  return {
    chartRows,
    series: [
      { key: "oldest", label: oldest },
      { key: "newest", label: newest },
    ],
  };
}

/** One cohort's share and counts for one milestone, or why it isn't shown. */
function milestoneCell(row: MilestoneRow | undefined): string {
  if (!row) return "";
  if (row.rate === null || row.reached === null || row.n === null) return SUPPRESSED_LABEL;
  return `${row.rate}% · ${formatCount(row.reached)} of ${formatCount(row.n)}`;
}

/** The exact shares behind the funnel, for every cohort that has had the window. */
export function milestoneTable(rows: MilestoneRow[]): ValuesTable {
  const cohorts = distinct(rows.map((row) => row.cohort));
  return {
    columns: cohorts,
    rows: distinct(rows.map((row) => row.milestone)).map((milestone) => ({
      label: milestone,
      cells: cohorts.map((cohort) =>
        milestoneCell(rows.find((row) => row.cohort === cohort && row.milestone === milestone)),
      ),
    })),
  };
}

/** Each part's share of one cohort's near-completers, stacked to 100. */
export function nearCompleterChart(rows: NearCompleterRow[]): { chartRows: ChartRow[]; series: ChartSeries[] } {
  const parts = distinct(rows.map((row) => row.part));
  // Part names hold spaces and punctuation, so the chart keys are positional.
  const keyOf = (part: string) => `part_${parts.indexOf(part)}`;
  const chartRows = distinct(rows.map((row) => row.cohort)).map((cohort) => {
    const chartRow: ChartRow = { cohort };
    for (const row of rows.filter((each) => each.cohort === cohort)) {
      if (row.share_of_pool !== null) chartRow[keyOf(row.part)] = row.share_of_pool;
    }
    return chartRow;
  });
  return { chartRows, series: parts.map((part) => ({ key: keyOf(part), label: part })) };
}

/** The counts behind the stacks, then each cohort's whole pool and how many seekers it's out of. */
export function nearCompleterTable(rows: NearCompleterRow[]): ValuesTable {
  const cohorts = distinct(rows.map((row) => row.cohort));
  const firstOf = (cohort: string) => rows.find((row) => row.cohort === cohort);
  return {
    columns: cohorts,
    rows: [
      ...distinct(rows.map((row) => row.part)).map((part) => ({
        label: part,
        cells: cohorts.map((cohort) => {
          const match = rows.find((row) => row.cohort === cohort && row.part === part);
          if (!match) return "";
          if (match.count === null || match.share_of_pool === null) return SUPPRESSED_LABEL;
          return `${formatCount(match.count)} · ${match.share_of_pool}%`;
        }),
      })),
      {
        label: "Near-completers",
        cells: cohorts.map((cohort) => {
          const row = firstOf(cohort);
          if (!row || row.pool === null || row.pool_rate === null) return SUPPRESSED_LABEL;
          return `${formatCount(row.pool)} · ${row.pool_rate}% of seekers`;
        }),
      },
      {
        label: "Associate-seekers counted",
        cells: cohorts.map((cohort) => {
          const seekers = firstOf(cohort)?.seekers ?? null;
          return seekers === null ? SUPPRESSED_LABEL : formatCount(seekers);
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

/** One bar per year-1 band: its rate, its gap from everyone else, and a caution when the gap may be chance. */
export function momentumBars(rows: MomentumRow[]): BarListItem[] {
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

/** A scale top a little above the largest value, rounded up to a step, so the bars use the width. */
export function scaleTop(values: (number | null)[], step: number): number {
  const largest = Math.max(0, ...values.filter((value): value is number => value !== null));
  return Math.max(step, Math.ceil((largest * 1.15) / step) * step);
}
