"use client";

import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";

import { ChatPageContext } from "@/components/chat/chat-page-context";
import { KeywordChatProvider } from "@/components/chat/keyword-chat";
import { BarList } from "@/components/sandbox/bar-list";
import { ChartCard } from "@/components/sandbox/chart-card";
import { DefinitionTooltip } from "@/components/sandbox/definition-tooltip";
import { KeywordButton } from "@/components/sandbox/keyword-button";
import { KpiGrid } from "@/components/sandbox/kpi-grid";
import { PartLegend } from "@/components/sandbox/part-swatch";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { type ChartSeries, seriesChartConfig } from "@/lib/charts";

import {
  allCohortsLegend,
  cohortColor,
  gapsByMeasure,
  HEADLINE_COUNT,
  headcountByTermSinceEntry,
  headcountLegend,
  headcountLineStyle,
  largestStudentsBehind,
  selectedLineLabel,
} from "./chart-config";
import { CourseLoadCard } from "./course-load";
import {
  type CohortLens,
  type CourseLoadFilterName,
  type CourseLoadFilters,
  DEFAULT_COHORT_LENS,
  gapsLoader,
  headcountLoader,
  kpisLoader,
  NO_FILTERS,
} from "./data";
import { FilterBar } from "./filters";
import { HomeStateMapCard } from "./home-state-map";
import { fromGap, fromKpi, fromMeasure, isKeywordMeasure, keywordLabel, suggestionsFor } from "./keywords";
import { ExportAllButton, ExportTileLink } from "./student-export";
import { SupplementalCard } from "./supplemental-card";

/** The whole view: the cohort and student filters, and every chart that follows them. */
export function CohortViews() {
  const [cohort, setCohort] = useState<CohortLens>(DEFAULT_COHORT_LENS);
  const [filters, setFilters] = useState<CourseLoadFilters>(NO_FILTERS);
  const loadKpis = useMemo(() => kpisLoader(cohort, filters), [cohort, filters]);
  const setFilter = (name: CourseLoadFilterName, value: string) =>
    setFilters((current) => ({ ...current, [name]: value }));
  const clearFilters = () => setFilters(NO_FILTERS);

  // The filter bar sits directly in the page column, so it stays pinned for the whole scroll. Only
  // from lg up: on a phone it wraps to five rows, and pinned it would cover half the screen.
  return (
    <KeywordChatProvider scopeOf={keywordLabel} suggestionsFor={suggestionsFor}>
      <div className="z-10 -mx-4 -my-2 border-b bg-background px-4 py-2 lg:sticky lg:top-0">
        <FilterBar cohort={cohort} filters={filters} onCohort={setCohort} onChange={setFilter} onClear={clearFilters} />
      </div>
      {/* Anchors on this page clear the sticky filter bar above. */}
      <div id="exec-headline" className="flex scroll-mt-16 flex-col gap-2">
        <div className="flex justify-end">
          <ExportAllButton cohort={cohort} filters={filters} />
        </div>
        <KpiGrid
          load={loadKpis}
          placeholderCount={HEADLINE_COUNT}
          labelOnTop
          columns={5}
          // A filter can leave no tile to show, e.g. on a single pooled year; the chips above say why.
          emptyText="No tiles for this selection."
          // Unfiltered, the tiles are published results, so the chat gets the specs behind them.
          renderMeta={(meta) => <ChatPageContext page={{ title: meta.title, filters: meta.filters, specs: meta.specs }} />}
          renderLabel={(kpi, meta) => {
            const definition = meta.definitions?.[kpi.label];
            if (!isKeywordMeasure(kpi.label)) {
              return (
                <DefinitionTooltip definition={definition}>
                  <span className={definition ? "underline decoration-dotted underline-offset-4" : undefined}>
                    {kpi.label}
                  </span>
                </DefinitionTooltip>
              );
            }
            return (
              <DefinitionTooltip definition={definition}>
                <KeywordButton keyword={fromKpi(kpi.label, cohort, filters, kpi.value)} label={kpi.label}>
                  {kpi.label}
                </KeywordButton>
              </DefinitionTooltip>
            );
          }}
          renderFooter={(kpi) => <ExportTileLink cohort={cohort} filters={filters} kpiId={kpi.id} />}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <EquityGaps cohort={cohort} />
        <Headcount cohort={cohort} filters={filters} />
      </div>

      <HomeStateMapCard cohort={cohort} filters={filters} />

      <CourseLoadCard cohort={cohort} filters={filters} />

      <SupplementalCard cohort={cohort} filters={filters} />
    </KeywordChatProvider>
  );
}

/** The largest equity gaps in the selected cohort's color, or stacked by cohort for all of them. */
function EquityGaps({ cohort }: { cohort: CohortLens }) {
  const load = useMemo(() => gapsLoader(cohort), [cohort]);
  const selected = selectedLineLabel(cohort);

  return (
    <ChartCard id="exec-equity-gaps" load={load} compact className="scroll-mt-16">
      {(data) => {
        if (data.rows.length === 0) {
          return <p className="text-sm text-muted-foreground">No gaps stand out from noise for this selection.</p>;
        }
        const max = largestStudentsBehind(data.rows);
        // The rows behind the bars, so a clicked group can carry its own rate, gap and count.
        const rowFor = new Map(data.rows.map((row) => [`${row.measure}|${row.group}`, row]));
        return (
          <div className="flex flex-col gap-3">
            <div className="grid gap-6 lg:grid-cols-3">
              {gapsByMeasure(data.rows).map(({ measure, items }) => (
                <section key={measure} className="flex min-w-0 flex-col gap-4">
                  <h4 className="text-sm font-semibold">
                    <DefinitionTooltip definition={data.meta.definitions?.[measure]}>
                      <KeywordButton keyword={fromMeasure(measure, cohort)} label={measure}>
                        {measure}
                      </KeywordButton>
                    </DefinitionTooltip>
                  </h4>
                  <BarList
                    items={items}
                    max={max}
                    color={selected === null ? undefined : cohortColor(selected)}
                    renderLabel={(group) => {
                      const row = rowFor.get(`${measure}|${group}`);
                      if (!row) return group;
                      return (
                        <KeywordButton keyword={fromGap(measure, row, cohort)} label={`${measure} for ${group}`}>
                          {group}
                        </KeywordButton>
                      );
                    }}
                  />
                </section>
              ))}
            </div>
            {selected === null && <PartLegend parts={allCohortsLegend()} />}
          </div>
        );
      }}
    </ChartCard>
  );
}

type HeadcountProps = { cohort: CohortLens; filters: CourseLoadFilters };

/** Headcount by terms since entry for the matching students, with the selected cohort drawn over the others. */
function Headcount({ cohort, filters }: HeadcountProps) {
  const load = useMemo(() => headcountLoader(filters), [filters]);
  return (
    <ChartCard id="exec-headcount" load={load} compact className="scroll-mt-16">
      {(data) => {
        if (data.rows.length === 0) {
          return <p className="text-sm text-muted-foreground">No data model is loaded.</p>;
        }
        const { chartRows, series } = headcountByTermSinceEntry(data.rows);
        return <HeadcountLines rows={chartRows} series={series} selected={selectedLineLabel(cohort)} />;
      }}
    </ChartCard>
  );
}

type HeadcountLinesProps = { rows: Record<string, string | number>[]; series: ChartSeries[]; selected: string | null };

/** Overlapping count lines aligned at each cohort's first term, with a legend. */
function HeadcountLines({ rows, series, selected }: HeadcountLinesProps) {
  // Drawn last, so the selected line sits on top of the faded ones.
  const drawOrder = [...series].sort((a, b) => Number(a.label === selected) - Number(b.label === selected));

  return (
    <div className="flex flex-col gap-3">
      <ChartContainer config={seriesChartConfig(series)} className="aspect-auto h-40 w-full">
        <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} strokeDasharray="2 4" />
          <XAxis dataKey="term" tickLine={false} axisLine={false} tickMargin={8} interval="equidistantPreserveStart" fontSize={11} />
          <YAxis tickLine={false} axisLine={false} width={36} fontSize={11} domain={[0, "auto"]} />
          <ChartTooltip cursor={false} content={<ChartTooltipContent indicator="line" />} />
          {drawOrder.map((line) => {
            const style = headcountLineStyle(line.label, selected);
            return (
              <Line
                key={line.key}
                dataKey={line.key}
                name={line.label}
                type="linear"
                stroke={style.color}
                strokeWidth={style.width}
                strokeOpacity={style.opacity}
                dot={style.showDots ? { r: 2, fill: style.color, strokeWidth: 0 } : false}
                isAnimationActive={false}
              />
            );
          })}
        </LineChart>
      </ChartContainer>
      <PartLegend parts={headcountLegend(series, selected)} />
    </div>
  );
}
