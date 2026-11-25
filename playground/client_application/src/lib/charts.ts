import type { Kpi } from "@/lib/sandbox";
import type { ChartConfig } from "@/components/ui/chart";

/** One line or bar series. `dashed` tells a series apart without relying on color. */
export type ChartSeries = {
  key: string;
  label: string;
  dashed?: boolean;
};

const SERIES_COLOR_COUNT = 5;

/** The chart color for the series at `index`, in the fixed order from globals.css. */
export function seriesColor(index: number): string {
  return `var(--chart-${(index % SERIES_COLOR_COUNT) + 1})`;
}

/** Chart config for shadcn/ui charts with each series in its own chart color. */
export function seriesChartConfig(series: ChartSeries[]): ChartConfig {
  return Object.fromEntries(series.map(({ key, label }, index) => [key, { label, color: seriesColor(index) }]));
}

export function formatPercent(value: unknown): string {
  return typeof value === "number" ? `${value}%` : "—";
}

export type BarListItem = {
  label: string;
  value: number | null;
  /** The value as shown next to the bar, e.g. "78%" or "5.1 terms". */
  display: string;
  /** A short caution beside the value, e.g. "few students". */
  note?: string;
  /** Splits the bar into colored parts, sized relative to each other. */
  segments?: BarSegment[];
};

/** One colored part of a stacked bar. `title` shows on hover. */
export type BarSegment = { key: string; value: number; color: string; title: string };

/** Turn chart rows into bars, given which field is the label and which is the value. */
export function toBarListItems<Row>(
  rows: Row[],
  labelOf: (row: Row) => string,
  valueOf: (row: Row) => number | null,
  formatValue: (value: number | null, row: Row) => string,
): BarListItem[] {
  return rows.map((row) => {
    const value = valueOf(row);
    return { label: labelOf(row), value, display: formatValue(value, row) };
  });
}

/** A bar's width as a percent of the track, capped at 100. */
export function barWidthPercent(value: number | null, max: number): number {
  if (value === null) return 0;
  return Math.min((value / max) * 100, 100);
}


/** A KPI's headline, e.g. "76%", "64 / 36" or "5.5" with the unit "terms" shown smaller. */
export function formatKpi(kpi: Kpi): { headline: string; unitLabel: string | null } {
  switch (kpi.unit) {
    case "percent":
      return { headline: formatPercent(kpi.value), unitLabel: null };
    case "split":
      return { headline: `${kpi.value} / ${kpi.secondary_value}`, unitLabel: null };
    case "terms":
      return { headline: `${kpi.value}`, unitLabel: "terms" };
    case "count":
      return { headline: formatCount(kpi.value), unitLabel: null };
  }
}

/**
 * Whether a line chart point is drawn filled. By default the first series has hollow points and a
 * dashed series filled ones; `isFilled` overrides that per row (e.g. to mark fall terms).
 */
export function isPointFilled<Row>(series: ChartSeries, row: Row | undefined, isFilled?: (row: Row) => boolean): boolean {
  if (isFilled && row) return isFilled(row);
  return Boolean(series.dashed);
}

/**
 * Fills for the parts of a whole, in order: the first three chart colors, then stripes. From the fifth part on,
 * the fills repeat.
 */
/** Stands in for the striped pattern until a chart points it at its own pattern id (see stripesFor). */
const STRIPES_FILL = "url(#part-stripes)";

const PART_FILLS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  STRIPES_FILL,
];

/** The fill for the part at `index`, and whether it's the striped one. */
export function partFill(index: number): { fill: string; isStriped: boolean } {
  const cycled = index % PART_FILLS.length;
  return { fill: PART_FILLS[cycled], isStriped: cycled === PART_FILLS.length - 1 };
}

const PART_LABEL_CLASSES = ["fill-chart-label-1", "fill-chart-label-2", "fill-chart-label-3", "fill-foreground"];

/** The text color that stays readable on the part at `index`. */
export function partLabelClass(index: number): string {
  return PART_LABEL_CLASSES[index % PART_LABEL_CLASSES.length];
}

/** Point a striped fill at one chart's own pattern, so two charts on a page don't share an SVG id. */
export function stripesFor(fill: string, patternId: string): string {
  return fill === STRIPES_FILL ? `url(#${patternId})` : fill;
}

/** The striped fill on its own, e.g. for the second bar of a pair. */
export const stripedPartFill = partFill(PART_FILLS.length - 1);

export type ShareSlice = { label: string; value: number; display: string; fill: string; isStriped: boolean };

/** Turn chart rows into pie or donut slices, in the order they arrive. */
export function toShareSlices<Row>(rows: Row[], labelOf: (row: Row) => string, valueOf: (row: Row) => number): ShareSlice[] {
  return rows.map((row, index) => ({
    label: labelOf(row),
    value: valueOf(row),
    display: formatPercent(valueOf(row)),
    ...partFill(index),
  }));
}

export function formatCount(value: unknown): string {
  return Number(value).toLocaleString("en-US");
}
