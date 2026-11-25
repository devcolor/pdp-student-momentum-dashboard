"use client";

import { FilterSelect } from "@/components/sandbox/filter-select";

import { type CohortLens, cohortLenses, cohortLensLabels } from "../executive-view/data";
import {
  type EquityDimension,
  equityDimensionLabels,
  equityDimensions,
  type EquityView,
  equityViewLabels,
  equityViews,
} from "./data";

export type SnapshotFilters = { cohort: CohortLens; view: EquityView; dimension: EquityDimension };

type FilterPaneProps = { filters: SnapshotFilters; onChange: (filters: SnapshotFilters) => void };

/** One horizontal pane of every filter on the page. It stays pinned while the page scrolls under it. */
export function FilterPane({ filters, onChange }: FilterPaneProps) {
  return (
    <div className="sticky top-0 z-20 rounded-xl border bg-background/95 px-4 py-3 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="grid max-w-3xl gap-3 sm:grid-cols-3">
        <FilterSelect id="snapshot-cohort" label="Cohort" values={cohortLenses} labels={cohortLensLabels} value={filters.cohort} onChange={(cohort) => onChange({ ...filters, cohort })} compact />
        <FilterSelect id="snapshot-view" label="Equity view" values={equityViews} labels={equityViewLabels} value={filters.view} onChange={(view) => onChange({ ...filters, view })} compact />
        <FilterSelect id="snapshot-split" label="Split by" values={equityDimensions} labels={equityDimensionLabels} value={filters.dimension} onChange={(dimension) => onChange({ ...filters, dimension })} compact />
      </div>
    </div>
  );
}
