"use client";

import { useMemo, useState } from "react";

import { BarList } from "@/components/sandbox/bar-list";
import { ChartCard } from "@/components/sandbox/chart-card";
import { GroupedBarChart } from "@/components/sandbox/grouped-bar-chart";
import { StackedBarChart } from "@/components/sandbox/stacked-bar-chart";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

import {
  milestoneChart,
  milestoneTable,
  momentumBars,
  nearCompleterChart,
  nearCompleterTable,
  scaleTop,
  type ValuesTable,
} from "./chart-config";
import {
  milestonesLoader,
  nearCompletersLoader,
  type Split,
  splitLabels,
  splits,
  type Window,
  windowLabels,
  windows,
  yearOneLoader,
} from "./data";

/** Among associate-seekers, the share reaching each credit milestone: oldest against newest cohort. */
export function MilestoneChart() {
  const [window, setWindow] = useState<Window>("3");
  const load = useMemo(() => milestonesLoader(window), [window]);

  return (
    <div className="flex flex-col gap-4">
      <Choice label="Count" value={window} values={windows} labels={windowLabels} onChange={setWindow} />
      <ChartCard load={load}>
        {(data) => {
          if (data.rows.length === 0) return <NothingToChart />;
          const chart = milestoneChart(data.rows);
          return (
            <div className="flex flex-col gap-4">
              {chart && <GroupedBarChart rows={chart.chartRows} categoryKey="milestone" series={chart.series} />}
              <ValuesGrid table={milestoneTable(data.rows)} />
            </div>
          );
        }}
      </ChartCard>
    </div>
  );
}

/** Near-completers per cohort, split into parts, with the pool's size in the table. */
export function NearCompleterChart() {
  const [window, setWindow] = useState<Window>("3");
  const [split, setSplit] = useState<Split>("credits_short");
  const load = useMemo(() => nearCompletersLoader(window, split), [window, split]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-4">
        <Choice label="Count" value={window} values={windows} labels={windowLabels} onChange={setWindow} />
        <Choice label="Split by" value={split} values={splits} labels={splitLabels} onChange={setSplit} />
      </div>
      <ChartCard load={load}>
        {(data) => {
          if (data.rows.length === 0) return <NothingToChart />;
          const { chartRows, series } = nearCompleterChart(data.rows);
          return (
            <div className="flex flex-col gap-4">
              <StackedBarChart rows={chartRows} categoryKey="cohort" series={series} />
              <ValuesGrid table={nearCompleterTable(data.rows)} />
            </div>
          );
        }}
      </ChartCard>
    </div>
  );
}

/** The associate rate for each year-1 credit band, against everyone else's. */
export function YearOneChart() {
  const [window, setWindow] = useState<Window>("3");
  const load = useMemo(() => yearOneLoader(window), [window]);

  return (
    <div className="flex flex-col gap-4">
      <Choice label="Count" value={window} values={windows} labels={windowLabels} onChange={setWindow} />
      <ChartCard load={load}>
        {(data) => {
          if (data.rows.length === 0) return <NothingToChart />;
          const everyone = data.everyone_rate ?? undefined;
          const max = scaleTop([...data.rows.map((row) => row.rate), data.everyone_rate], 10);
          return (
            <div className="flex flex-col gap-4">
              <BarList items={momentumBars(data.rows)} max={max} reference={everyone} />
              {everyone !== undefined && (
                <p className="text-xs text-muted-foreground">Every associate-seeker: {everyone}%</p>
              )}
            </div>
          );
        }}
      </ChartCard>
    </div>
  );
}

type ChoiceProps<Value extends string> = {
  label: string;
  value: Value;
  values: readonly Value[];
  labels: Record<Value, string>;
  onChange: (value: Value) => void;
};

/** A row of buttons for a few choices, with one always picked. */
function Choice<Value extends string>({ label, value, values, labels, onChange }: ChoiceProps<Value>) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <ToggleGroup
        aria-label={label}
        multiple={false}
        value={[value]}
        onValueChange={(picked) => {
          const next = values.find((option) => option === picked[0]);
          if (next) onChange(next);
        }}
        variant="outline"
        size="sm"
        className="max-w-full flex-wrap"
      >
        {values.map((option) => (
          <ToggleGroupItem key={option} value={option}>
            {labels[option]}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </div>
  );
}

/** Shown when no cohort has had the window yet; the note under the chart says why. */
function NothingToChart() {
  return <p className="text-sm text-muted-foreground">Nothing to chart for this view yet.</p>;
}

/** The exact numbers behind a chart, one row per series or part. */
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
