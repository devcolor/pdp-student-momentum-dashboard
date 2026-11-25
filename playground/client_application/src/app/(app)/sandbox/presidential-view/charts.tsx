"use client";

import { useContext, useMemo, useState } from "react";
import { Sparkles } from "lucide-react";
import { Line, LineChart, ReferenceDot, XAxis, YAxis } from "recharts";

import { ChatPageContext } from "@/components/chat/chat-page-context";
import { KeywordChatProvider } from "@/components/chat/keyword-chat";
import { explainKpiLabel } from "@/components/sandbox/definition-tooltip";
import { FilterSelect } from "@/components/sandbox/filter-select";
import { KpiGrid, trendStatusColors } from "@/components/sandbox/kpi-grid";
import { PinnedFilters } from "@/components/sandbox/pinned-filters";
import { Button } from "@/components/ui/button";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { useApiResource } from "@/hooks/use-api-resource";
import { ChatSessionContext } from "@/hooks/use-chat-session";
import { useKeywordChat } from "@/hooks/use-keyword-chat";
import type { Kpi } from "@/lib/sandbox";

import { type CohortLens, cohortLenses, cohortLensLabels, DEFAULT_COHORT_LENS } from "../executive-view/data";
import { SNAPSHOT_KPI_COUNT, snapshotKpisLoader } from "../student-success/data";
import { changeLabel, formatMetric, type MetricTrend, metricTrends } from "./chart-config";
import { type TrendRow, trendsLoader } from "./data";
import { fromPresidentialKpi, scopeOf, suggestionsFor } from "./keywords";

/** The presidential view: five KPI cards for one cohort, each with its trend across cohorts. */
export function PresidentialViews() {
  const [cohort, setCohort] = useState<CohortLens>(DEFAULT_COHORT_LENS);
  const loadKpis = useMemo(() => snapshotKpisLoader(cohort), [cohort]);
  const { resource } = useApiResource(trendsLoader);

  const trends = useMemo(() => {
    if (resource.status !== "success") return new Map<string, MetricTrend>();
    return new Map(metricTrends(resource.data.rows).map((trend) => [trend.metric, trend]));
  }, [resource]);
  // The raw rows, null until loaded: the chat needs each point's partial flag, which the drawn lines fold away.
  const trendRows = resource.status === "success" ? resource.data.rows : null;

  return (
    <KeywordChatProvider scopeOf={scopeOf} suggestionsFor={suggestionsFor}>
      <section className="flex flex-col gap-3">
        <PinnedFilters>
          <div className="max-w-56">
            <FilterSelect
              id="presidential-cohort"
              label="Cohort"
              value={cohort}
              values={cohortLenses}
              labels={cohortLensLabels}
              onChange={setCohort}
              compact
            />
          </div>
        </PinnedFilters>
        <KpiGrid
          load={loadKpis}
          placeholderCount={SNAPSHOT_KPI_COUNT}
          labelOnTop
          columns={5}
          renderLabel={explainKpiLabel}
          // The cards are calculated live, so their specs are empty: that tells the chat they aren't published results.
          renderMeta={(meta) => <ChatPageContext page={{ title: meta.title, filters: meta.filters, specs: meta.specs }} />}
          renderFooter={(kpi) => {
            const trend = trends.get(kpi.id);
            // Match the card's pill: green better, red worse, gray the same or no comparison.
            const color = trendStatusColors[kpi.trend?.status ?? "neutral"];
            return (
              <div className="flex flex-col gap-3">
                {trend && <TrendSparkline trend={trend} cohort={cohort} color={color} />}
                {/* Hidden, like the sparkline, when the trends can't load: the chat needs the card's trend. */}
                {resource.status !== "error" && (
                  <ExplainWithAiButton
                    kpi={kpi}
                    cohort={cohort}
                    trend={trendRows?.filter((row) => row.metric === kpi.id) ?? null}
                  />
                )}
              </div>
            );
          }}
        />
        <p className="text-xs text-muted-foreground">
          Lines show each metric for every entering cohort. Dashed parts are cohorts not yet fully observed, so they will likely rise.
        </p>
      </section>
    </KeywordChatProvider>
  );
}

type TrendSparklineProps = { trend: MetricTrend; cohort: CohortLens; color: string };

/** A small line of one metric by entering cohort, with the selected cohort's point ringed. */
function TrendSparkline({ trend, cohort, color }: TrendSparklineProps) {
  const change = changeLabel(trend);
  const config = {
    observed: { label: trend.label, color },
    partial: { label: `${trend.label} (partly observed)`, color },
  };
  const selected = trend.points.find((point) => point.cohort === cohort);
  const selectedValue = selected?.observed ?? selected?.partial ?? null;

  return (
    <div className="flex flex-col gap-1 border-t pt-2">
      <ChartContainer config={config} className="aspect-auto h-16 w-full">
        <LineChart data={trend.points} margin={{ top: 6, right: 6, bottom: 0, left: 6 }}>
          <XAxis dataKey="cohort" hide />
          {/* Fit each metric's own range, so a few points' change is visible in a small card. */}
          <YAxis hide domain={[(min: number) => min * 0.9, (max: number) => max * 1.05]} />
          <ChartTooltip
            cursor={false}
            content={<ChartTooltipContent indicator="line" formatter={(value) => formatMetric(Number(value), trend.unit)} />}
          />
          <Line dataKey="observed" stroke={color} strokeWidth={2} dot={{ r: 2, fill: color, strokeWidth: 0 }} isAnimationActive={false} />
          <Line
            dataKey="partial"
            stroke={color}
            strokeWidth={2}
            strokeDasharray="3 3"
            dot={{ r: 2, fill: "var(--background)", stroke: color }}
            isAnimationActive={false}
          />
          {selectedValue !== null && selected && (
            <ReferenceDot x={selected.cohort} y={selectedValue} r={5} fill="none" stroke="var(--foreground)" strokeWidth={1.5} />
          )}
        </LineChart>
      </ChartContainer>
      <p className="text-[11px] text-muted-foreground">
        {change ?? `${trend.points[0]?.cohort} to ${trend.points.at(-1)?.cohort}`}
      </p>
    </div>
  );
}

/** trend is null while the trends load. */
type ExplainWithAiButtonProps = { kpi: Kpi; cohort: CohortLens; trend: TrendRow[] | null };

/** Opens the shell's chat about one KPI card, with its trend and suggested questions. Only on the chat pages. */
function ExplainWithAiButton({ kpi, cohort, trend }: ExplainWithAiButtonProps) {
  const session = useContext(ChatSessionContext);
  const { openKeyword } = useKeywordChat();
  // The server needs at least one trend point, so a card whose trend has none gets no button.
  if (!session?.availableHere || trend?.length === 0) return null;

  return (
    <Button
      variant="outline"
      size="sm"
      className="self-start"
      disabled={trend === null}
      // Starts with the visible text, so voice control can find it by what it says.
      aria-label={`Explain with AI: ${kpi.label}`}
      onClick={(event) => {
        if (trend) openKeyword(fromPresidentialKpi(kpi, cohort, trend), event.currentTarget);
      }}
    >
      <Sparkles aria-hidden />
      Explain with AI
    </Button>
  );
}
