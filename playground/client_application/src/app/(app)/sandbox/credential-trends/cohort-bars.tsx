"use client";

import { Bar, BarChart, LabelList, XAxis, YAxis } from "recharts";

import { PartStripes, usePartStripesId } from "@/components/sandbox/part-stripes";
import { PartLegend } from "@/components/sandbox/part-swatch";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import {
  type ChartSeries,
  formatPercent,
  partFill,
  seriesChartConfig,
  stripedPartFill,
  stripesFor,
} from "@/lib/charts";

type CohortBarsProps = {
  rows: Record<string, string | number>[];
  categoryKey: string;
  series: ChartSeries[];
  /** The top of the scale. Rates here sit far below 100%, so the shared 0-to-100 charts would flatten them. */
  max: number;
  /** Stack the parts into one column per category, instead of placing them side by side. */
  stacked?: boolean;
};

/** Bars per category on a scale fitted to the data: rates side by side, or counts stacked. */
export function CohortBars({ rows, categoryKey, series, max, stacked = false }: CohortBarsProps) {
  const stripesId = usePartStripesId();
  // A pair reads as solid against striped, like the shared grouped bars; a stack steps through the part fills.
  const fills = series.map((_, index) => (!stacked && series.length === 2 && index === 1 ? stripedPartFill : partFill(index)));

  return (
    <div className="flex flex-col gap-3">
      <ChartContainer config={seriesChartConfig(series)} className="aspect-auto h-60 w-full">
        <BarChart data={rows} margin={{ top: 22, right: 0, bottom: 0, left: 0 }} barGap={6}>
          <defs>
            <PartStripes id={stripesId} />
          </defs>
          <XAxis dataKey={categoryKey} tickLine={false} axisLine={false} tickMargin={8} interval={0} fontSize={11} />
          <YAxis hide domain={[0, max]} />
          <ChartTooltip cursor={false} content={<ChartTooltipContent indicator="dot" />} />
          {series.map((part, index) => (
            <Bar
              key={part.key}
              dataKey={part.key}
              stackId={stacked ? "parts" : undefined}
              fill={stripesFor(fills[index].fill, stripesId)}
              stroke={stacked ? "var(--background)" : fills[index].isStriped ? "var(--chart-2)" : undefined}
              strokeWidth={stacked ? 2 : fills[index].isStriped ? 1.25 : 0}
              radius={stacked ? 0 : [6, 6, 0, 0]}
              isAnimationActive={false}
            >
              {!stacked && (
                <LabelList
                  dataKey={part.key}
                  position="top"
                  className="fill-foreground text-xs font-semibold"
                  formatter={formatPercent}
                />
              )}
            </Bar>
          ))}
        </BarChart>
      </ChartContainer>
      <PartLegend parts={series.map((part, index) => ({ ...part, ...fills[index] }))} />
    </div>
  );
}
