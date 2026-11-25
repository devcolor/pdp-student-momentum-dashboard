"use client";

import { useMemo, useState } from "react";

import { BarList } from "@/components/sandbox/bar-list";
import { ChartCard } from "@/components/sandbox/chart-card";
import { FilterSelect } from "@/components/sandbox/filter-select";
import { PinnedFilters } from "@/components/sandbox/pinned-filters";

import { groupRateBars } from "./chart-config";
import {
  cohortLabels,
  cohorts,
  groupByLabels,
  groupBys,
  groupRateLoader,
  measureLabels,
  measures,
  type Cohort,
  type GroupBy,
  type Measure,
} from "./data";

/** A complete pattern: local filter state becomes typed query parameters and reloads a ChartCard. */
export function Charts() {
  const [measure, setMeasure] = useState<Measure>("gateway_math");
  const [cohort, setCohort] = useState<Cohort>("2022-23");
  const [groupBy, setGroupBy] = useState<GroupBy>("gender");
  const load = useMemo(
    () => groupRateLoader(measure, cohort, groupBy),
    [measure, cohort, groupBy],
  );

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <PinnedFilters>
        <div className="grid gap-4 sm:grid-cols-3">
          <FilterSelect
            id="cohort"
            label="Cohort"
            value={cohort}
            values={cohorts}
            labels={cohortLabels}
            onChange={setCohort}
          />
          <FilterSelect
            id="group-by"
            label="Group by"
            value={groupBy}
            values={groupBys}
            labels={groupByLabels}
            onChange={setGroupBy}
          />
          <FilterSelect
            id="measure"
            label="Measure"
            value={measure}
            values={measures}
            labels={measureLabels}
            onChange={setMeasure}
          />
        </div>
      </PinnedFilters>

      <ChartCard load={load}>
        {(data) =>
          data.rows.length > 0 ? (
            <BarList items={groupRateBars(data.rows)} />
          ) : (
            <p className="text-sm text-muted-foreground">This fixture does not include this combination yet.</p>
          )
        }
      </ChartCard>
    </div>
  );
}
