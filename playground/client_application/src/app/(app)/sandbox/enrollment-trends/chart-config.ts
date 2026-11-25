/** /sandbox/enrollment-trends: turn the server's long rows into chart rows and table rows. */

import { type ChartSeries, formatCount } from "@/lib/charts";

import type { Entering, EnteringRow, TermRow } from "./data";

export const SUPPRESSED_LABEL = "<10";

export type ValuesTable = { columns: string[]; rows: { label: string; cells: string[] }[] };

type Stacked = { chartRows: Record<string, string | number>[]; series: ChartSeries[]; table: ValuesTable };

type StackSpec<Row> = {
  categoryKey: string;
  categoryOf: (row: Row) => string;
  partOf: (row: Row) => string;
  chartValueOf: (row: Row) => number | null;
  cellOf: (row: Row) => string;
  totalOf: (row: Row) => number;
};

/** Distinct values, in the order they first appear. */
function distinct(values: string[]): string[] {
  return [...new Set(values)];
}

/** Pivot long rows into one chart row per category, plus a values table with a total line. */
function stack<Row>(rows: Row[], spec: StackSpec<Row>): Stacked {
  const categories = distinct(rows.map(spec.categoryOf));
  const parts = distinct(rows.map(spec.partOf));
  // Group labels can hold spaces and brackets, so the chart keys are positional.
  const keyOf = (part: string) => `part_${parts.indexOf(part)}`;
  const rowsIn = (category: string) => rows.filter((row) => spec.categoryOf(row) === category);

  const chartRows = categories.map((category) => {
    const chartRow: Record<string, string | number> = { [spec.categoryKey]: category };
    for (const row of rowsIn(category)) {
      const value = spec.chartValueOf(row);
      if (value !== null) chartRow[keyOf(spec.partOf(row))] = value;
    }
    return chartRow;
  });

  const partRows = parts.map((part) => ({
    label: part,
    cells: categories.map((category) => {
      const match = rowsIn(category).find((row) => spec.partOf(row) === part);
      return match ? spec.cellOf(match) : "";
    }),
  }));
  const totalRow = {
    label: "Total",
    cells: categories.map((category) => formatCount(spec.totalOf(rowsIn(category)[0]))),
  };

  // A group suppressed in every category has nothing to draw, but stays in the table.
  const drawn = parts.filter((part) => rows.some((row) => spec.partOf(row) === part && spec.chartValueOf(row) !== null));

  return {
    chartRows,
    series: drawn.map((part) => ({ key: keyOf(part), label: part })),
    table: { columns: categories, rows: [...partRows, totalRow] },
  };
}

/** Each cohort's bar is its groups' shares; the table shows the counts behind them. */
export function enteringStack(rows: Entering["rows"]): Stacked {
  return stack<EnteringRow>(rows, {
    categoryKey: "cohort",
    categoryOf: (row) => row.cohort,
    partOf: (row) => row.group,
    chartValueOf: (row) => row.share,
    cellOf: (row) => (row.n === null ? SUPPRESSED_LABEL : `${formatCount(row.n)} · ${row.share}%`),
    totalOf: (row) => row.cohort_total,
  });
}

/** Each term's bar is its headcount, stacked oldest cohort at the bottom. */
export function byTermStack(rows: TermRow[]): Stacked {
  return stack<TermRow>(rows, {
    categoryKey: "term",
    categoryOf: (row) => row.term,
    partOf: (row) => `${row.cohort} cohort`,
    chartValueOf: (row) => row.n,
    cellOf: (row) => (row.n === null ? SUPPRESSED_LABEL : formatCount(row.n)),
    totalOf: (row) => row.term_total,
  });
}
