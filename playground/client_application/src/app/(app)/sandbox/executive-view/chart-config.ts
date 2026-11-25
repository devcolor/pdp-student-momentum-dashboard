/** /sandbox/executive-view: turn the server's gap rows into one bar list per measure. */

import type { LegendPart } from "@/components/sandbox/part-swatch";
import { type BarListItem, type ChartSeries, formatCount, seriesColor } from "@/lib/charts";

import type { TermRow } from "../enrollment-trends/data";
import { type CohortLens, cohortLenses, cohortPoolYears, type GapRow } from "./data";

export const HEADLINE_COUNT = 5;

const FADED_LINE_COLOR = "var(--muted-foreground)";

const cohortYears = cohortLenses.filter((lens) => lens !== "all");

/** The name a cohort's line goes by. */
function cohortLineLabel(cohort: string): string {
  return `${cohort} cohort`;
}

/** The line a cohort button puts in focus, or null when all cohorts are shown equally. */
export function selectedLineLabel(cohort: CohortLens): string | null {
  return cohort === "all" ? null : cohortLineLabel(cohort);
}

/** Pivot headcount to one row per term since entry, so every cohort's Term 1 lines up. */
export function headcountByTermSinceEntry(rows: TermRow[]): { chartRows: Record<string, string | number>[]; series: ChartSeries[] } {
  const terms = [...new Set(rows.map((row) => row.term))];
  const cohorts = [...new Set(rows.map((row) => row.cohort))].sort();
  const keyOf = (cohort: string) => `cohort_${cohorts.indexOf(cohort)}`;
  const firstTermOf = (cohort: string) => terms.findIndex((term) => rows.some((row) => row.cohort === cohort && row.term === term));

  const chartRows: Record<string, string | number>[] = terms.map((_, index) => ({ term: `Term ${index + 1}` }));
  for (const row of rows) {
    // A suppressed count leaves a gap in the line, never a zero.
    if (row.n !== null) {
      const termsSinceEntry = terms.indexOf(row.term) - firstTermOf(row.cohort);
      chartRows[termsSinceEntry][keyOf(row.cohort)] = row.n;
    }
  }

  return {
    chartRows,
    series: cohorts.map((cohort) => ({ key: keyOf(cohort), label: cohortLineLabel(cohort) })),
  };
}

/** A cohort's color, fixed by its year so it matches across buttons, lines and bars. */
export function cohortColor(label: string): string {
  return seriesColor(cohortYears.findIndex((year) => label.startsWith(year)));
}

/** One legend entry per pooled cohort, for the stacked bars of the pooled lens. */
export function allCohortsLegend(): LegendPart[] {
  return cohortPoolYears.map((year) => ({ key: year, label: cohortLineLabel(year), fill: cohortColor(year), isStriped: false }));
}

export type HeadcountLineStyle = { color: string; width: number; opacity: number; showDots: boolean };

/** Bold color for the selected cohort, thin gray for the rest, and color for all when none is selected. */
export function headcountLineStyle(label: string, selected: string | null): HeadcountLineStyle {
  if (selected === null) return { color: cohortColor(label), width: 2, opacity: 1, showDots: true };
  if (label === selected) return { color: cohortColor(label), width: 2.5, opacity: 1, showDots: true };
  return { color: FADED_LINE_COLOR, width: 1.25, opacity: 0.5, showDots: false };
}

/** The legend: every cohort when none is selected, otherwise the selected one and "Other cohorts". */
export function headcountLegend(series: ChartSeries[], selected: string | null): LegendPart[] {
  if (selected === null) {
    return series.map((line) => ({ key: line.key, label: line.label, fill: cohortColor(line.label), isStriped: false }));
  }
  return [
    { key: "selected", label: selected, fill: cohortColor(selected), isStriped: false },
    { key: "others", label: "Other cohorts", fill: FADED_LINE_COLOR, isStriped: false },
  ];
}

export type MeasureGaps = { measure: string; items: BarListItem[] };

/** One gap as a bar: its length is students behind, the note is the gap itself. */
function gapBar(row: GapRow): BarListItem {
  return {
    label: row.group,
    value: row.students_behind,
    display: `${formatCount(row.students_behind)} students`,
    note: `−${Math.abs(row.gap_pts).toFixed(1)} pts`,
    segments: row.by_cohort?.map((share) => ({
      key: share.cohort,
      value: share.students_behind,
      color: cohortColor(share.cohort),
      title: `${cohortLineLabel(share.cohort)}: ${formatCount(share.students_behind)} students behind`,
    })),
  };
}

/** Gap rows grouped by measure, in the order the server sent them. */
export function gapsByMeasure(rows: GapRow[]): MeasureGaps[] {
  const measures = [...new Set(rows.map((row) => row.measure))];
  return measures.map((measure) => ({
    measure,
    items: rows.filter((row) => row.measure === measure).map(gapBar),
  }));
}

/** The longest bar across every measure, so bar lengths compare between lists. */
export function largestStudentsBehind(rows: GapRow[]): number {
  return Math.max(...rows.map((row) => row.students_behind));
}
