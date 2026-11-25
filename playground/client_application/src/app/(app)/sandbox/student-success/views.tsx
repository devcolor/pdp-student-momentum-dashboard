"use client";

import { useMemo, useState } from "react";

import { explainKpiLabel } from "@/components/sandbox/definition-tooltip";
import { KpiGrid } from "@/components/sandbox/kpi-grid";

import { DEFAULT_COHORT_LENS } from "../executive-view/data";
import { ActionBoardCard } from "./actions";
import { type EquityDimension, type School, SNAPSHOT_KPI_COUNT, snapshotKpisLoader } from "./data";
import { EquityAnalysisCard } from "./equity";
import { FilterPane, type SnapshotFilters } from "./filters";

/** The snapshot below its pinned filter pane: KPIs, the equity analysis and the action board. */
export function SnapshotViews({ initialDimension = "race", school = "ccac" }: { initialDimension?: EquityDimension; school?: School }) {
  const [filters, setFilters] = useState<SnapshotFilters>({ cohort: DEFAULT_COHORT_LENS, view: "population", dimension: initialDimension });
  const loadKpis = useMemo(() => snapshotKpisLoader(filters.cohort), [filters.cohort]);

  return (
    <>
      <FilterPane filters={filters} onChange={setFilters} />
      <KpiGrid load={loadKpis} placeholderCount={SNAPSHOT_KPI_COUNT} columns={5} labelOnTop renderLabel={explainKpiLabel} />
      <EquityAnalysisCard cohort={filters.cohort} view={filters.view} dimension={filters.dimension} school={school} />
      <ActionBoardCard cohort={filters.cohort} dimension={filters.dimension} school={school} />
    </>
  );
}
