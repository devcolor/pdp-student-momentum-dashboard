"use client";

import { Bar, BarChart, LabelList, XAxis, YAxis } from "recharts";

import { PartStripes, usePartStripesId } from "@/components/sandbox/part-stripes";
import { PartLegend } from "@/components/sandbox/part-swatch";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { type ChartSeries, formatPercent, partFill, partLabelClass, seriesChartConfig, stripesFor } from "@/lib/charts";

type StackedBarChartProps = {
  rows: Record<string, string | number>[];
  categoryKey: string;
  /** The parts of each bar, from the bottom up. Each row's parts add up to 100, unless `counts` is set. */
  series: ChartSeries[];
  /** Draw raw counts: the scale fits the data, and bar labels are left off for a table to carry. */
  counts?: boolean;
  /** Draw each part as its own bar beside the others; a table carries the values, as with `counts`. */
  sideBySide?: boolean;
};

/** One column per category, split into its parts, in black and white. */
export function StackedBarChart({ rows, categoryKey, series, counts = false, sideBySide = false }: StackedBarChartProps) {
  const stripesId = usePartStripesId();
  const fitsData = counts || sideBySide;

  return (
    <div className="flex flex-col gap-3">
      <ChartContainer config={seriesChartConfig(series)} className="aspect-auto h-56 w-full">
        <BarChart data={rows} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <PartStripes id={stripesId} />
          </defs>
          <XAxis dataKey={categoryKey} tickLine={false} axisLine={false} tickMargin={8} interval={counts ? "equidistantPreserveStart" : 0} fontSize={11} />
          <YAxis hide domain={fitsData ? [0, "auto"] : [0, 100]} />
          <ChartTooltip cursor={false} content={<ChartTooltipContent indicator="dot" />} />
          {series.map((part, index) => (
            <Bar
              key={part.key}
              dataKey={part.key}
              stackId={sideBySide ? undefined : "parts"}
              fill={stripesFor(partFill(index).fill, stripesId)}
              // The outline separates stacked parts; on narrow side-by-side bars it would hide them.
              stroke={sideBySide ? "none" : "var(--background)"}
              strokeWidth={2}
              isAnimationActive={false}
            >
              {/* Dark ink on the lightest part, light ink on the two darker ones. */}
              {!fitsData && (
                <LabelList
                  dataKey={part.key}
                  position="center"
                  className={index < 2 ? "fill-background text-[11px] font-semibold" : "fill-foreground text-[11px] font-semibold"}
                  formatter={formatPercent}
                />
              )}
            </Bar>
          ))}
        </BarChart>
      </ChartContainer>
      <PartLegend parts={series.map((part, index) => ({ ...part, ...partFill(index) }))} />
    </div>
  );
}
