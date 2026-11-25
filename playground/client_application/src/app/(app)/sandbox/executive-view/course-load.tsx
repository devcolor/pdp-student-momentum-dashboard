"use client";

import { ArrowDown, ArrowRight, ArrowUp } from "lucide-react";
import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, XAxis, YAxis } from "recharts";

import { ChartCard } from "@/components/sandbox/chart-card";
import { FilterSelect } from "@/components/sandbox/filter-select";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { formatPercent, seriesColor } from "@/lib/charts";

import {
  type CohortLens,
  type CourseLoad,
  type CourseLoadFilters,
  courseLoadLoader,
  DEFAULT_GRANULARITY,
  type Granularity,
  granularities,
  granularityLabels,
  type LoadCurve,
} from "./data";

// Two curves at most, in chart theme colors, so they follow the Charts setting. Slots 1 and 4 are
// the only pair that passes the colorblind checks in every palette the app offers; slot 2 fails in
// IBM. Everyone is also dashed, like the comparison lines on other charts.
const MATCH_COLOR = seriesColor(0);
const EVERYONE_COLOR = seriesColor(3);
const EVERYONE_DASH = "5 4";
// Across hidden bands, a faint dotted line keeps the curve whole without showing a value.
const BRIDGE_DASH = "1 4";
// Short names for the tooltip, where space is tight. The legend and table keep the long ones.
const MATCH_SHORT = "Matching";
const EVERYONE_SHORT = "Everyone";
const CHART_CONFIG = {
  match: { label: MATCH_SHORT, color: MATCH_COLOR },
  everyone: { label: EVERYONE_SHORT, color: EVERYONE_COLOR },
};
const gapIcons = { more: ArrowUp, same: ArrowRight, less: ArrowDown };
type GapDirection = keyof typeof gapIcons;
// The gap pill takes the color of whichever curve is higher, so it says who is higher, not good or bad.
const gapColors: Record<GapDirection, string> = {
  more: MATCH_COLOR,
  same: "var(--muted-foreground)",
  less: EVERYONE_COLOR,
};
// The x-axis is labelled every 12 credits, whatever the band size.
const TICK_EVERY_CREDITS = 12;

type CourseLoadCardProps = { cohort: CohortLens; filters: CourseLoadFilters };

/** Year-1 course load: one curve for the students the page's filters match, over everyone's, dashed. */
export function CourseLoadCard({ cohort, filters }: CourseLoadCardProps) {
  // The band size is this chart's own display setting, so it stays here, not with the page's filters.
  const [granularity, setGranularity] = useState<Granularity>(DEFAULT_GRANULARITY);
  const load = useMemo(() => courseLoadLoader(cohort, filters, granularity), [cohort, filters, granularity]);

  return (
    <ChartCard
      id="exec-course-load"
      load={load}
      compact
      className="scroll-mt-16"
      controls={
        <div className="max-w-56">
          <FilterSelect
            id="course-load-granularity"
            label="Credit bands"
            value={granularity}
            values={granularities}
            labels={granularityLabels}
            onChange={setGranularity}
          />
        </div>
      }
      details={(data) => <LoadTable data={data} />}
    >
      {(data) => <LoadChart data={data} granularity={granularity} />}
    </ChartCard>
  );
}

/** The matching students' curve over everyone's, or everyone's alone with no filter on. */
function LoadChart({ data, granularity }: { data: CourseLoad; granularity: Granularity }) {
  const isFiltered = data.selected !== null;
  const matchCurve = isFiltered ? data.selected : data.everyone;
  const everyoneCurve = isFiltered ? data.everyone : null;
  const yMax = sharedMax([data.everyone, data.selected]);
  // Every credit makes 37 points per curve, so its dots get smaller to keep the curve readable.
  const dotRadius = data.bands.length > 13 ? 2.5 : 4.5;

  const rows = data.bands.map((band, index) => ({
    band,
    match: matchCurve?.shares[index] ?? null,
    everyone: everyoneCurve?.shares[index] ?? null,
  }));
  const ticks = data.bands.filter((band) => Number.parseInt(band, 10) % TICK_EVERY_CREDITS === 0);
  const bandsText = granularity === "1" ? "one credit at a time" : `in bands of ${granularity}`;

  return (
    <div className="flex flex-col gap-3">
      {isFiltered && <LineKey />}
      {data.hidden_reason && <p className="text-sm text-muted-foreground">{data.hidden_reason}</p>}
      <ChartContainer config={CHART_CONFIG} className="aspect-auto h-56 w-full">
        <LineChart data={rows} margin={{ top: 12, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} strokeDasharray="2 4" />
          <XAxis dataKey="band" ticks={ticks} interval={0} tickLine={false} axisLine={false} tickMargin={6} fontSize={11} />
          <YAxis
            domain={[0, yMax]}
            ticks={[0, yMax / 2, yMax]}
            tickFormatter={(value: number) => `${value}%`}
            tickLine={false}
            axisLine={false}
            width={36}
            fontSize={11}
          />
          <ReferenceLine
            x={data.on_track_band}
            stroke="var(--muted-foreground)"
            strokeDasharray="2 3"
            label={{ value: "On track", position: "insideTopRight", fontSize: 11, fill: "var(--muted-foreground)" }}
          />
          <ChartTooltip cursor={false} content={<LoadTooltip isFiltered={isFiltered} />} />
          {everyoneCurve && <Bridge dataKey="everyone" color={EVERYONE_COLOR} />}
          {everyoneCurve && (
            <Line
              dataKey="everyone"
              name="Everyone in the cohort"
              type="monotone"
              stroke={EVERYONE_COLOR}
              strokeWidth={1.75}
              strokeDasharray={EVERYONE_DASH}
              dot={themeDot(EVERYONE_COLOR, dotRadius)}
              connectNulls={false}
              isAnimationActive={false}
            />
          )}
          {matchCurve && <Bridge dataKey="match" color={MATCH_COLOR} />}
          {matchCurve && (
            <Line
              dataKey="match"
              name={isFiltered ? "Students who match" : "Everyone"}
              type="monotone"
              stroke={MATCH_COLOR}
              strokeWidth={1.75}
              dot={themeDot(MATCH_COLOR, dotRadius)}
              connectNulls={false}
              isAnimationActive={false}
            />
          )}
        </LineChart>
      </ChartContainer>
      <p className="text-xs text-muted-foreground">
        Credits attempted in year 1, {bandsText}. The &quot;On track&quot; line is {data.on_track_band} credits: on
        track for a 60-credit associate in 2 years. Faint dotted stretches cross bands under 10 students, which are
        hidden: they keep the curve whole but show no value.
      </p>
    </div>
  );
}

type LoadRow = { band: string; match: number | null; everyone: number | null };
type LoadTooltipProps = { active?: boolean; payload?: { payload: LoadRow }[]; isFiltered: boolean };

/** The hovered band in credits, each curve's share, and how far the matching students sit from everyone. */
function LoadTooltip({ active, payload, isFiltered }: LoadTooltipProps) {
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;

  return (
    <div className="grid min-w-36 gap-1.5 rounded-lg border border-border/50 bg-background px-2.5 py-1.5 text-xs shadow-xl">
      <div className="font-medium">{creditsLabel(row.band)}</div>
      <TooltipRow color={MATCH_COLOR} name={isFiltered ? MATCH_SHORT : EVERYONE_SHORT} share={row.match} />
      {isFiltered && <TooltipRow color={EVERYONE_COLOR} name={EVERYONE_SHORT} share={row.everyone} isDashed />}
      {isFiltered && <GapPill match={row.match} everyone={row.everyone} />}
    </div>
  );
}

type TooltipRowProps = { color: string; name: string; share: number | null; isDashed?: boolean };

/** One curve in the tooltip: its line style, short name and share. */
function TooltipRow({ color, name, share, isDashed = false }: TooltipRowProps) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground">
        <LineSwatch color={color} isDashed={isDashed} />
        {name}
      </span>
      <span className="font-mono font-medium text-foreground tabular-nums">
        {share === null ? "Hidden" : formatPercent(share)}
      </span>
    </div>
  );
}

/** How many points the matching students' share sits above or below everyone's, in the higher curve's color. */
function GapPill({ match, everyone }: { match: number | null; everyone: number | null }) {
  if (match === null || everyone === null) return null;
  // Rounded first, so float noise like 5.000000000000002 doesn't show and a tie reads as the same.
  const gap = Math.round((match - everyone) * 10) / 10;
  const direction = gapDirection(gap);
  const Icon = gapIcons[direction];
  const color = gapColors[direction];

  return (
    <p
      className="inline-flex w-fit items-center gap-1 rounded-full px-2 py-0.5 font-medium text-foreground tabular-nums"
      style={{ backgroundColor: `color-mix(in oklab, ${color} 18%, transparent)` }}
    >
      <Icon className="size-3.5" style={{ color }} aria-hidden />
      {formatGap(gap)} vs everyone
    </p>
  );
}

/** More, less, or the same. */
function gapDirection(gap: number): GapDirection {
  if (gap > 0) return "more";
  if (gap < 0) return "less";
  return "same";
}

/** A signed gap in points, like the credential trends page: "+5.4 pts" or "-2.3 pts". */
function formatGap(gap: number): string {
  return `${gap > 0 ? "+" : ""}${gap} pts`;
}

/** A band with its unit: "6-8 credits", "36+ credits", "1 credit". */
function creditsLabel(band: string): string {
  return band === "1" ? "1 credit" : `${band} credits`;
}

/** A faint dotted line through a curve's shown points, joining across its hidden bands. */
function Bridge({ dataKey, color }: { dataKey: string; color: string }) {
  return (
    <Line
      dataKey={dataKey}
      type="monotone"
      stroke={color}
      strokeWidth={1.5}
      strokeOpacity={0.6}
      strokeDasharray={BRIDGE_DASH}
      dot={false}
      activeDot={false}
      connectNulls
      legendType="none"
      tooltipType="none"
      isAnimationActive={false}
    />
  );
}

type DotProps = { cx?: number; cy?: number; index?: number; value?: number | null };

/** A filled dot on each shown band, as the shared trend chart draws them. Hidden bands get none. */
function themeDot(color: string, radius: number) {
  return function Dot(dot: DotProps) {
    if (dot.value === null || dot.value === undefined) return <g key={dot.index} />;
    return <circle key={dot.index} cx={dot.cx} cy={dot.cy} r={radius} stroke={color} strokeWidth={1.75} fill={color} />;
  };
}

/** The legend once filtered: solid for the students who match, dashed for everyone in the cohort. */
function LineKey() {
  return (
    <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
      <span>
        <LineSwatch color={MATCH_COLOR} /> Students who match
      </span>
      <span>
        <LineSwatch color={EVERYONE_COLOR} isDashed /> Everyone in the cohort
      </span>
    </div>
  );
}

/** A short line in a series color, solid or dashed like its curve, as the trend chart's table shows. */
function LineSwatch({ color, isDashed = false }: { color: string; isDashed?: boolean }) {
  return (
    <span
      aria-hidden
      className="mr-1.5 inline-block w-4 border-t-2 align-middle"
      style={{ borderTopColor: color, borderTopStyle: isDashed ? "dashed" : "solid" }}
    />
  );
}

/** The numbers behind the curves, so no reading depends on color or hover. */
function LoadTable({ data }: { data: CourseLoad }) {
  const rows: { label: string; curve: LoadCurve }[] = [{ label: "Everyone in the cohort", curve: data.everyone }];
  if (data.selected) rows.push({ label: "Students who match", curve: data.selected });

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px] tabular-nums sm:text-xs">
        <thead>
          <tr className="text-muted-foreground">
            <th scope="col" className="py-1.5 pr-2 text-left font-normal">Group</th>
            <th scope="col" className="py-1.5 text-right font-normal">Students</th>
            <th scope="col" className="py-1.5 text-right font-normal">Median credits</th>
            <th scope="col" className="py-1.5 text-right font-normal">Under 12</th>
            <th scope="col" className="py-1.5 text-right font-normal">30 or more</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ label, curve }) => (
            <tr key={label} className="border-t">
              <th scope="row" className="py-1.5 pr-2 text-left font-normal whitespace-nowrap">
                {label}
              </th>
              {/* Hidden, not "<10": a curve can be hidden for leaving out fewer than 10 instead. */}
              <td className="py-1.5 text-right font-semibold">{curve.n === null ? "Hidden" : curve.n.toLocaleString()}</td>
              <td className="py-1.5 text-right">{curve.median_credits ?? "—"}</td>
              <td className="py-1.5 text-right">{formatPercent(curve.under_12_pct)}</td>
              <td className="py-1.5 text-right">{formatPercent(curve.on_track_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** One y-axis top for both curves. A multiple of 10 keeps its middle tick whole. */
function sharedMax(curves: (LoadCurve | null)[]): number {
  const shares = curves
    .flatMap((curve) => curve?.shares ?? [])
    .filter((share): share is number => share !== null);
  return Math.max(10, Math.ceil(Math.max(0, ...shares) / 10) * 10);
}
