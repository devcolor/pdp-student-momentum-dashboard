"use client";

import { useMemo, useState } from "react";

import { ChartCard } from "@/components/sandbox/chart-card";
import { FilterSelect } from "@/components/sandbox/filter-select";
import { KpiGrid } from "@/components/sandbox/kpi-grid";
import { StackedBarChart } from "@/components/sandbox/stacked-bar-chart";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

import { byTermStack, enteringStack, type ValuesTable } from "./chart-config";
import { byTermLoader, enteringLoader, KPI_COUNT, kpisLoader, type SplitBy, splitByLabels, splitBys } from "./data";

type BarLayout = "side-by-side" | "stacked";

/** The KPI row, then both enrollment charts side by side: who enters each cohort, and headcount by term. */
export function Charts() {
  const [splitBy, setSplitBy] = useState<SplitBy>("enrollment_type");
  const [enteringLayout, setEnteringLayout] = useState<BarLayout>("side-by-side");
  const [byTermLayout, setByTermLayout] = useState<BarLayout>("side-by-side");
  const loadEntering = useMemo(() => enteringLoader(splitBy), [splitBy]);

  return (
    <>
      <div id="enrollment-headline" className="scroll-mt-6">
        <KpiGrid load={kpisLoader} placeholderCount={KPI_COUNT} labelOnTop />
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <ChartCard
          id="enrollment-entering"
          load={loadEntering}
          controls={
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div className="w-full max-w-xs">
                <FilterSelect
                  id="split-by"
                  label="Split entering students by"
                  value={splitBy}
                  values={splitBys}
                  labels={splitByLabels}
                  onChange={setSplitBy}
                />
              </div>
              <BarLayoutToggle label="Bar layout for entering students" value={enteringLayout} onChange={setEnteringLayout} />
            </div>
          }
          details={(data) => data.rows.length > 0 && <ValuesGrid table={enteringStack(data.rows).table} />}
        >
          {(data) => {
            if (data.rows.length === 0) return <NoData />;
            const { chartRows, series } = enteringStack(data.rows);
            return (
              <StackedBarChart
                rows={chartRows}
                categoryKey="cohort"
                series={series}
                sideBySide={enteringLayout === "side-by-side"}
              />
            );
          }}
        </ChartCard>

        <ChartCard
          id="enrollment-by-term"
          load={byTermLoader}
          controls={
            <div className="flex justify-end">
              <BarLayoutToggle label="Bar layout for headcount by term" value={byTermLayout} onChange={setByTermLayout} />
            </div>
          }
          details={(data) => data.rows.length > 0 && <ValuesGrid table={byTermStack(data.rows).table} />}
        >
          {(data) => {
            if (data.rows.length === 0) return <NoData />;
            const { chartRows, series } = byTermStack(data.rows);
            return (
              <StackedBarChart
                rows={chartRows}
                categoryKey="term"
                series={series}
                counts
                sideBySide={byTermLayout === "side-by-side"}
              />
            );
          }}
        </ChartCard>
      </div>
    </>
  );
}

type BarLayoutToggleProps = { label: string; value: BarLayout; onChange: (value: BarLayout) => void };

/** Switches one chart between bars beside each other and bars stacked into one column. */
function BarLayoutToggle({ label, value, onChange }: BarLayoutToggleProps) {
  return (
    <ToggleGroup
      aria-label={label}
      multiple={false}
      value={[value]}
      onValueChange={(values) => {
        const next = values[0];
        if (next === "side-by-side" || next === "stacked") onChange(next);
      }}
      variant="outline"
      size="sm"
      className="max-w-full flex-wrap"
    >
      <ToggleGroupItem value="side-by-side">Side by side</ToggleGroupItem>
      <ToggleGroupItem value="stacked">Stacked</ToggleGroupItem>
    </ToggleGroup>
  );
}

/** Shown when the database has the tables but no data model has been loaded. */
function NoData() {
  return <p className="text-sm text-muted-foreground">No data model is loaded. Load one from the Sandbox pipeline.</p>;
}

/** The exact numbers behind a chart, one row per group and a total line. */
function ValuesGrid({ table }: { table: ValuesTable }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px] tabular-nums sm:text-xs">
        <thead>
          <tr>
            <td />
            {table.columns.map((column) => (
              <th key={column} scope="col" className="px-2 py-1.5 text-right font-normal whitespace-nowrap text-muted-foreground">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row) => (
            <tr key={row.label} className="border-t">
              <th scope="row" className="py-1.5 pr-2 text-left font-normal whitespace-nowrap text-muted-foreground">
                {row.label}
              </th>
              {row.cells.map((cell, index) => (
                <td key={table.columns[index]} className="px-2 py-1.5 text-right font-semibold whitespace-nowrap">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
