"use client";

import { ArrowDown, ArrowRight, ArrowUp } from "lucide-react";

import { LoadError } from "@/components/load-error";
import { FilterChips } from "@/components/sandbox/filter-chips";
import { StatTile, StatTileSkeleton } from "@/components/stat-tile";
import { useApiResource } from "@/hooks/use-api-resource";
import { formatKpi } from "@/lib/charts";
import type { ChartMeta, Kpi, KpiResponse, KpiTrend } from "@/lib/sandbox";
import { cn } from "@/lib/utils";

// Two tiles a row on small screens; on large screens, four, or five for a five-tile row.
const kpiGridClasses = { 4: "grid grid-cols-2 gap-3 lg:grid-cols-4", 5: "grid grid-cols-2 gap-3 lg:grid-cols-5" };

const trendIcons = { up: ArrowUp, down: ArrowDown, flat: ArrowRight };

/** Plain colors for each trend status, for charts that should match the pills. */
export const trendStatusColors = {
  good: "var(--color-emerald-500)",
  neutral: "var(--muted-foreground)",
  bad: "var(--color-red-500)",
};

const trendStatusClasses = {
  good: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  neutral: "bg-muted text-muted-foreground",
  bad: "bg-red-500/15 text-red-700 dark:text-red-400",
};

// Screen readers get the judgment that the color shows.
const trendStatusWords = { good: "Better:", neutral: "", bad: "Worse:" };

/** An arrow and the change in words, colored by whether the move is better, the same, or worse. */
export function TrendPill({ trend }: { trend: KpiTrend }) {
  const Icon = trendIcons[trend.direction];
  // Color always follows the server's good/bad judgment, never the arrow's direction.
  const { status } = trend;
  return (
    <p className={cn("my-1 inline-flex w-fit items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium tabular-nums", trendStatusClasses[status])}>
      <Icon className="size-3.5" aria-hidden />
      <span className="sr-only">{trendStatusWords[status]}</span>
      {trend.label}
    </p>
  );
}

type KpiTileProps = {
  kpi: Kpi;
  meta: ChartMeta;
  labelOnTop: boolean;
  renderLabel?: KpiLabelRenderer;
  footer?: React.ReactNode;
};

/** One KPI as a stat tile, with its trend pill. */
function KpiTile({ kpi, meta, labelOnTop, renderLabel, footer }: KpiTileProps) {
  const { headline, unitLabel } = formatKpi(kpi);
  return (
    <li>
      <StatTile
        value={headline}
        unit={unitLabel}
        trend={kpi.trend && <TrendPill trend={kpi.trend} />}
        label={renderLabel ? renderLabel(kpi, meta) : kpi.label}
        footer={footer}
        labelOnTop={labelOnTop}
        detail={kpi.detail}
      />
    </li>
  );
}

/** Wraps a tile's label, e.g. to make it open a chat or explain it. Gets the KPI and the meta
 * it arrived with, so a renderer can read meta.definitions. */
export type KpiLabelRenderer = (kpi: Kpi, meta: ChartMeta) => React.ReactNode;

type KpiGridProps = {
  load: () => Promise<KpiResponse>;
  /** How many placeholder tiles to show while loading. */
  placeholderCount: number;
  /** Puts each tile's label above its number. */
  labelOnTop?: boolean;
  /** Tiles per row on large screens. */
  columns?: 4 | 5;
  /** Wraps each tile's label. Leave it out for plain text. */
  renderLabel?: KpiLabelRenderer;
  /** Extra content at the bottom of each tile, such as the KPI's trend. */
  renderFooter?: (kpi: Kpi) => React.ReactNode;
  /** Drawn once with the loaded meta, e.g. to register the page with the chat. */
  renderMeta?: (meta: ChartMeta) => React.ReactNode;
  /** Shown in place of the tiles when none came back. Leave it out to draw the empty grid as before. */
  emptyText?: string;
};

/** KPI stat cards, as at the top of the briefs' dashboards. */
export function KpiGrid({
  load,
  placeholderCount,
  labelOnTop = false,
  columns = 4,
  renderLabel,
  renderFooter,
  renderMeta,
  emptyText,
}: KpiGridProps) {
  const { resource, retry } = useApiResource(load);

  if (resource.status === "error") {
    return (
      <LoadError
        title="The KPIs couldn't load."
        message={resource.message}
        onRetry={retry}
        className="rounded-2xl border p-8"
      />
    );
  }

  if (resource.status === "loading") {
    return (
      <ul className={kpiGridClasses[columns]} aria-busy="true" aria-label="Loading KPIs">
        {Array.from({ length: placeholderCount }, (_, placeholderIndex) => (
          <li key={placeholderIndex}>
            <StatTileSkeleton />
          </li>
        ))}
      </ul>
    );
  }

  const { meta, items } = resource.data;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">{meta.title}</span>
        <FilterChips filters={meta.filters} />
      </div>
      {renderMeta?.(meta)}
      {items.length === 0 && emptyText ? (
        <p className="text-sm text-muted-foreground">{emptyText}</p>
      ) : (
        <ul className={kpiGridClasses[columns]}>
          {items.map((kpi) => (
            <KpiTile key={kpi.id} kpi={kpi} meta={meta} labelOnTop={labelOnTop} renderLabel={renderLabel}
              footer={renderFooter?.(kpi)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
