/** /sandbox/presidential-view: turn trend rows into one small line chart per metric. */

import { formatCount } from "@/lib/charts";

import type { TrendRow } from "./data";

export type MetricPoint = {
  cohort: string;
  /** Fully observed value, drawn as a solid line. */
  observed: number | null;
  /** Partly observed value, drawn dashed; repeats the last observed point so the lines join. */
  partial: number | null;
  n: number | null;
};

export type MetricTrend = {
  metric: string;
  label: string;
  unit: TrendRow["unit"];
  latest: TrendRow | undefined;
  points: MetricPoint[];
};

/** Group rows by metric in server order, splitting each line into observed and partial parts. */
export function metricTrends(rows: TrendRow[]): MetricTrend[] {
  const metrics = [...new Set(rows.map((row) => row.metric))];
  return metrics.map((metric) => {
    const own = rows.filter((row) => row.metric === metric);
    const points: MetricPoint[] = own.map((row) => ({
      cohort: row.cohort,
      observed: row.partial ? null : row.value,
      partial: row.partial ? row.value : null,
      n: row.n,
    }));
    // Join the dashed part to the solid part at the last fully observed cohort.
    const firstPartial = own.findIndex((row) => row.partial);
    if (firstPartial > 0) points[firstPartial - 1].partial = points[firstPartial - 1].observed;

    return {
      metric,
      label: own[0].label,
      unit: own[0].unit,
      latest: own.filter((row) => row.value !== null).at(-1),
      points,
    };
  });
}

/** A value as the metric shows it. */
export function formatMetric(value: number | null | undefined, unit: TrendRow["unit"]): string {
  if (value === null || value === undefined) return "—";
  return unit === "count" ? formatCount(value) : `${value.toFixed(1)}%`;
}

/** The change across fully observed cohorts, e.g. "+2.4 pts, 2021-22 to 2023-24", or null. */
export function changeLabel(trend: MetricTrend): string | null {
  // Partly observed cohorts are left out, so an unfinished window can't read as a drop.
  const observed = trend.points.filter((point) => point.observed !== null);
  if (observed.length < 2) return null;
  const start = observed[0];
  const end = observed[observed.length - 1];
  const diff = (end.observed ?? 0) - (start.observed ?? 0);
  const sign = diff >= 0 ? "+" : "−";
  const amount = trend.unit === "count" ? formatCount(Math.abs(Math.round(diff))) : `${Math.abs(diff).toFixed(1)} pts`;
  return `${sign}${amount}, ${start.cohort} to ${end.cohort}`;
}
