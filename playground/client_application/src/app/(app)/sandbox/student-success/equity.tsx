"use client";

import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { BarList } from "@/components/sandbox/bar-list";
import { ChartCard } from "@/components/sandbox/chart-card";
import { type LegendPart, PartLegend } from "@/components/sandbox/part-swatch";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { type BarListItem, type ChartSeries, formatCount, seriesChartConfig, seriesColor } from "@/lib/charts";

import { type CohortLens, cohortLensLabels } from "../executive-view/data";
import { type EquityAnalysis, type EquityDimension, equityLoader, type EquityView, type School } from "./data";

type EquityAnalysisCardProps = { cohort: CohortLens; view: EquityView; dimension: EquityDimension; school?: School };

/** The Student Success & Equity Analysis card. The page's filter pane picks the view and split. */
export function EquityAnalysisCard({ cohort, view, dimension, school = "ccac" }: EquityAnalysisCardProps) {
  const load = useMemo(() => equityLoader(cohort, dimension), [cohort, dimension]);

  return (
    <ChartCard id="success-equity" load={load}>
      {(data) => {
        if (data.groups.length === 0) {
          return <p className="text-sm text-muted-foreground">No students in this selection.</p>;
        }
        if (view === "population") return <PopulationView data={data} heading={populationHeading(cohort, school)} />;
        if (view === "programs") return <ProgramsView data={data} />;
        return <MomentumView data={data} />;
      }}
    </ChartCard>
  );
}

/** The share chart's heading: MVSU names the selected cohort. */
function populationHeading(cohort: CohortLens, school: School): string {
  if (school === "ccac") return "Share of entering students";
  return cohort === "all" ? `Demographics of the ${cohortLensLabels.all} cohorts` : `Demographics of the ${cohortLensLabels[cohort]} cohort`;
}

/** Each group's share of the cohort, beside its retention against everyone. */
function PopulationView({ data, heading }: { data: EquityAnalysis; heading: string }) {
  const shares: BarListItem[] = data.groups.map((group) => ({
    label: group.group,
    value: group.share,
    display: group.share === null || group.n === null ? "Hidden" : `${group.share}% · ${formatCount(group.n)}`,
  }));
  const retention: BarListItem[] = data.groups.map((group) => ({
    label: group.group,
    value: group.retention,
    display: group.retention === null ? "—" : `${group.retention}%`,
    note: gapNote(group.retention_gap_pts, group.likely_noise),
  }));

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="flex min-w-0 flex-col gap-4">
        <h4 className="text-sm font-semibold">{heading}</h4>
        <BarList items={shares} />
      </section>
      <section className="flex min-w-0 flex-col gap-4">
        <h4 className="text-sm font-semibold">
          Retention <span className="font-normal text-muted-foreground">· line marks everyone, {data.everyone.retention ?? "—"}%</span>
        </h4>
        <BarList items={retention} reference={data.everyone.retention ?? undefined} />
      </section>
    </div>
  );
}

/** The gap in points beside a retention bar; noise reads as "about the same". */
function gapNote(gapPts: number | null, likelyNoise: boolean | null): string | undefined {
  if (gapPts === null) return undefined;
  if (likelyNoise) return "about the same";
  const sign = gapPts < 0 ? "−" : "+";
  return `${sign}${Math.abs(gapPts).toFixed(1)} pts`;
}

/** The largest programs, each bar split into the dimension's groups. */
function ProgramsView({ data }: { data: EquityAnalysis }) {
  const groupColor = (group: string) => seriesColor(data.groups.findIndex((row) => row.group === group));
  const largest = Math.max(...data.programs.map((program) => program.n));

  const items: BarListItem[] = data.programs.map((program) => {
    const hidden = program.segments.some((segment) => segment.n === null);
    return {
      label: program.label,
      value: program.n,
      display: `${formatCount(program.n)} students`,
      note: hidden ? "some groups hidden" : undefined,
      segments: program.segments
        .filter((segment) => segment.n !== null)
        .map((segment) => ({
          key: segment.group,
          value: segment.n ?? 0,
          color: groupColor(segment.group),
          title: `${segment.group}: ${formatCount(segment.n)} students`,
        })),
    };
  });
  const legend: LegendPart[] = data.groups.map((group) => ({ key: group.group, label: group.group, fill: groupColor(group.group), isStriped: false }));

  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">No program has 10 or more students in this selection.</p>;
  }
  return (
    <div className="flex flex-col gap-4">
      <BarList items={items} max={largest} />
      <PartLegend parts={legend} />
    </div>
  );
}

/** Year-1 credit milestones by group, with everyone first for comparison. */
function MomentumView({ data }: { data: EquityAnalysis }) {
  const series: ChartSeries[] = data.milestones.map((label, index) => ({ key: `m${index}`, label }));
  const shown = [data.everyone, ...data.groups.filter((group) => group.milestones.every((rate) => rate !== null))];
  const rows = shown.map((group) => ({
    group: group.group,
    ...Object.fromEntries(group.milestones.map((rate, index) => [`m${index}`, rate])),
  }));
  const hiddenCount = data.groups.length + 1 - shown.length;

  return (
    <div className="flex flex-col gap-3">
      <h4 className="text-sm font-semibold">Share who earned each credit milestone in year 1</h4>
      <ChartContainer config={seriesChartConfig(series)} className="aspect-auto h-64 w-full">
        <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} strokeDasharray="2 4" />
          <XAxis dataKey="group" tickLine={false} axisLine={false} tickMargin={8} interval={0} fontSize={11} />
          <YAxis tickLine={false} axisLine={false} width={36} fontSize={11} domain={[0, 100]} unit="%" />
          <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
          {series.map((line) => (
            <Bar key={line.key} dataKey={line.key} name={line.label} fill={`var(--color-${line.key})`} radius={[3, 3, 0, 0]} isAnimationActive={false} />
          ))}
        </BarChart>
      </ChartContainer>
      <PartLegend parts={series.map((line, index) => ({ key: line.key, label: line.label, fill: seriesColor(index), isStriped: false }))} />
      {hiddenCount > 0 && <p className="text-xs text-muted-foreground">Hidden groups are left out, to protect small counts.</p>}
    </div>
  );
}
