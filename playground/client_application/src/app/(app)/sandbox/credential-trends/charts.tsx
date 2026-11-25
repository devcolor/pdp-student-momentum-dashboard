"use client";

import { useMemo, useState } from "react";

import { BarList } from "@/components/sandbox/bar-list";
import { ChartCard } from "@/components/sandbox/chart-card";
import { StackedBarChart } from "@/components/sandbox/stacked-bar-chart";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

import {
  cohortRateChart,
  cohortRateTable,
  driverBars,
  pathwayChart,
  pathwayTable,
  programChart,
  programTable,
  scaleTop,
  type ValuesTable,
} from "./chart-config";
import { CohortBars } from "./cohort-bars";
import {
  byCohortLoader,
  byProgramLoader,
  type Credential,
  credentialLabels,
  credentials,
  driversLoader,
  type Factor,
  factorLabels,
  factors,
  type FixedWindow,
  fixedWindows,
  pathwaysLoader,
  type Window,
  windowLabels,
  windows,
} from "./data";

const fixedWindowLabels: Record<FixedWindow, string> = {
  "1": windowLabels["1"],
  "2": windowLabels["2"],
  "3": windowLabels["3"],
};

/** Associate and certificate rates by cohort, counted so far or on the same clock for every cohort. */
export function TrendChart() {
  const [window, setWindow] = useState<Window>("so_far");
  const load = useMemo(() => byCohortLoader(window), [window]);

  return (
    <div className="flex flex-col gap-4">
      <Choice label="Count credentials" value={window} values={windows} labels={windowLabels} onChange={setWindow} />
      <ChartCard load={load}>
        {(data) => {
          if (data.rows.length === 0) return <NoData />;
          const { chartRows, series, max } = cohortRateChart(data.rows);
          return (
            <div className="flex flex-col gap-4">
              <CohortBars rows={chartRows} categoryKey="cohort" series={series} max={max} />
              <ValuesGrid table={cohortRateTable(data.rows)} />
            </div>
          );
        }}
      </ChartCard>
    </div>
  );
}

/** Earners per cohort, split by the largest programs, so one program's swing is visible. */
export function ProgramChart() {
  const [credential, setCredential] = useState<Credential>("certificate");
  const [window, setWindow] = useState<FixedWindow>("1");
  const load = useMemo(() => byProgramLoader(credential, window), [credential, window]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-4">
        <Choice label="Credential" value={credential} values={credentials} labels={credentialLabels} onChange={setCredential} />
        <Choice label="Count" value={window} values={fixedWindows} labels={fixedWindowLabels} onChange={setWindow} />
      </div>
      <ChartCard load={load}>
        {(data) => {
          if (data.rows.length === 0) return <NoData />;
          const { chartRows, series, max } = programChart(data.rows);
          return (
            <div className="flex flex-col gap-4">
              <CohortBars rows={chartRows} categoryKey="cohort" series={series} max={max} stacked />
              <ValuesGrid table={programTable(data.rows)} />
            </div>
          );
        }}
      </ChartCard>
    </div>
  );
}

/** For credential earners: associate only, certificate only, or both, by what they came for. */
export function PathwayChart() {
  const [window, setWindow] = useState<FixedWindow>("3");
  const load = useMemo(() => pathwaysLoader(window), [window]);

  return (
    <div className="flex flex-col gap-4">
      <Choice label="Count" value={window} values={fixedWindows} labels={fixedWindowLabels} onChange={setWindow} />
      <ChartCard load={load}>
        {(data) => {
          if (data.rows.length === 0) return <NoData />;
          const { chartRows, series } = pathwayChart(data.rows);
          return (
            <div className="flex flex-col gap-4">
              <StackedBarChart rows={chartRows} categoryKey="sought" series={series} />
              <ValuesGrid table={pathwayTable(data.rows)} />
            </div>
          );
        }}
      </ChartCard>
    </div>
  );
}

/** Among students who came for a credential, each group's rate against everyone else's. */
export function DriverChart() {
  const [credential, setCredential] = useState<Credential>("associate");
  const [window, setWindow] = useState<FixedWindow>("3");
  const [factor, setFactor] = useState<Factor>("gateway_math");
  const load = useMemo(() => driversLoader(credential, window, factor), [credential, window, factor]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-4">
        <Choice label="Credential" value={credential} values={credentials} labels={credentialLabels} onChange={setCredential} />
        <Choice label="Count" value={window} values={fixedWindows} labels={fixedWindowLabels} onChange={setWindow} />
        <FilterSelect id="driver-factor" label="Split by" value={factor} values={factors} labels={factorLabels} onChange={setFactor} />
      </div>
      <ChartCard load={load}>
        {(data) => {
          if (data.rows.length === 0) return <NoData />;
          const everyone = data.everyone_rate ?? undefined;
          const max = scaleTop([...data.rows.map((row) => row.rate), data.everyone_rate], 10);
          return (
            <div className="flex flex-col gap-4">
              <BarList items={driverBars(data.rows)} max={max} reference={everyone} />
              {everyone !== undefined && (
                <p className="text-xs text-muted-foreground">Everyone who came for it: {everyone}%</p>
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

type FilterSelectProps<Value extends string> = ChoiceProps<Value> & { id: string };

/** A dropdown for a longer list of choices. */
function FilterSelect<Value extends string>({ id, label, value, values, labels, onChange }: FilterSelectProps<Value>) {
  return (
    <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground" htmlFor={id}>
      {label}
      <select
        id={id}
        value={value}
        onChange={(event) => {
          const next = values.find((option) => option === event.target.value);
          if (next) onChange(next);
        }}
        className="h-8 rounded-md border bg-background px-2 text-sm font-normal text-foreground shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
      >
        {values.map((option) => (
          <option key={option} value={option}>
            {labels[option]}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Shown when the database has the tables but no data model has been loaded. */
function NoData() {
  return <p className="text-sm text-muted-foreground">No data model is loaded. Load one from the Sandbox pipeline.</p>;
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
