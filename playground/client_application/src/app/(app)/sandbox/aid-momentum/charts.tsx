"use client";

import { useMemo, useState } from "react";

import { ChatPageContext } from "@/components/chat/chat-page-context";
import { BarList } from "@/components/sandbox/bar-list";
import { ChartCard } from "@/components/sandbox/chart-card";
import { FilterSelect } from "@/components/sandbox/filter-select";
import type { BarListItem } from "@/lib/charts";

import {
  type BandGapRow,
  type BandRow,
  bandsLoader,
  gapsLoader,
  lowerIsBetter,
  type Measure,
  measureLabels,
  measures,
  type PellRow,
  pellLoader,
} from "./data";

/** A hidden group's bar, so a suppressed band still has a row and never reads as zero. */
const HIDDEN = "hidden to protect small counts";

function percent(value: number | null) {
  return value === null ? "—" : `${value.toFixed(1)}%`;
}

/** Bars for the band chart. The everyone row becomes the reference line, not a bar. */
function bandItems(rows: BandRow[]): { items: BarListItem[]; reference?: number } {
  const everyone = rows.find((row) => row.is_everyone);
  const items = rows
    .filter((row) => !row.is_everyone)
    .map((row) => ({
      label: row.band,
      value: row.rate,
      display: percent(row.rate),
      note: row.rate === null ? HIDDEN : row.n === null ? undefined : `n=${row.n.toLocaleString()}`,
    }));
  return { items, reference: everyone?.rate ?? undefined };
}

/** Bars for the gap chart: distance from everyone else, with the noise check called out. */
function gapItems(rows: BandGapRow[]): BarListItem[] {
  return rows.map((row) => ({
    label: `${row.band} (rank ${row.rank} of ${row.ranked_of})`,
    value: Math.abs(row.gap_pts),
    display: `${row.gap_pts > 0 ? "+" : ""}${row.gap_pts.toFixed(2)} pts`,
    note: row.likely_noise
      ? "likely noise"
      : `95% CI ${row.ci_low.toFixed(1)} to ${row.ci_high.toFixed(1)}`,
  }));
}

/** Bars for the comparison chart, labelled by which data each series came from. */
function pellItems(rows: PellRow[], series: PellRow["series"]): BarListItem[] {
  return rows
    .filter((row) => row.series === series)
    .map((row) => ({
      label: row.group,
      value: row.rate,
      display: percent(row.rate),
      note: row.rate === null ? HIDDEN : row.n === null ? undefined : `n=${row.n.toLocaleString()}`,
    }));
}

/** The band chart: one bar per unmet need band, with every student as the reference line. */
function BandChart({ rows, worseIsHigher }: { rows: BandRow[]; worseIsHigher: boolean }) {
  if (rows.length === 0) return <NoData />;
  const { items, reference } = bandItems(rows);
  return (
    <div className="flex flex-col gap-3">
      <BarList items={items} reference={reference} />
      {reference !== undefined && (
        <p className="text-xs text-muted-foreground">
          The line marks every student, {percent(reference)}.{" "}
          {worseIsHigher ? "A bar past it is behind." : "A bar short of it is behind."}
        </p>
      )}
    </div>
  );
}

function NoData({ message }: { message?: string }) {
  return (
    <p className="text-sm text-muted-foreground">
      {message ?? "No rows yet. Publish the shared measures first (python -m measures.publish from the repo root)."}
    </p>
  );
}

/** The three unmet need charts, all driven by one measure filter. `initialMeasure` comes from the page's link. */
export function Charts({ initialMeasure }: { initialMeasure: Measure }) {
  const [measure, setMeasure] = useState<Measure>(initialMeasure);
  const loadBands = useMemo(() => bandsLoader(measure), [measure]);
  const loadGaps = useMemo(() => gapsLoader(measure), [measure]);
  const loadPell = useMemo(() => pellLoader(measure), [measure]);
  const worseIsHigher = lowerIsBetter.has(measure);

  const picker = (
    <div className="w-full max-w-xs">
      <FilterSelect
        id="measure"
        label="Measure"
        value={measure}
        values={measures}
        labels={measureLabels}
        onChange={setMeasure}
      />
    </div>
  );

  return (
    <div className="flex flex-col gap-4">
      <ChartCard id="aid-by-band" load={loadBands} controls={picker}>
        {(data) => (
          <>
            <ChatPageContext page={{ title: data.meta.title, filters: data.meta.filters, specs: data.meta.specs }} />
            <BandChart rows={data.rows} worseIsHigher={worseIsHigher} />
          </>
        )}
      </ChartCard>

      <div className="grid gap-4 xl:grid-cols-2">
        <ChartCard id="aid-gaps" load={loadGaps}>
          {(data) =>
            data.rows.length === 0 ? (
              <NoData message={data.meta.takeaway ?? undefined} />
            ) : (
              <BarList items={gapItems(data.rows)} max={Math.max(...data.rows.map((r) => Math.abs(r.gap_pts)))} />
            )
          }
        </ChartCard>

        <ChartCard id="aid-pell" load={loadPell}>
          {(data) => {
            if (data.rows.length === 0) return <NoData />;
            return (
              <div className="flex flex-col gap-5">
                <section className="flex flex-col gap-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Pell status · in the mock data
                  </h3>
                  <BarList items={pellItems(data.rows, "pell")} />
                </section>
                <section className="flex flex-col gap-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Unmet need band · synthetic stand-in
                  </h3>
                  <BarList items={pellItems(data.rows, "unmet_need_band")} />
                </section>
              </div>
            );
          }}
        </ChartCard>
      </div>
    </div>
  );
}
