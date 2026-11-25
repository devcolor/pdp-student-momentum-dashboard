"use client";

import { X } from "lucide-react";
import { useMemo } from "react";

import { FilterSelect } from "@/components/sandbox/filter-select";
import { Button } from "@/components/ui/button";
import { useApiResource } from "@/hooks/use-api-resource";

import {
  type CohortLens,
  cohortLenses,
  cohortLensLabels,
  type CourseLoadFilterName,
  type CourseLoadFilters,
  courseLoadFilterMenus,
  courseLoadFilterNames,
  courseLoadProgramsLoader,
  isFiltered,
} from "./data";

// The student filters in A-Z order of their labels; Cohort stays first in the bar, before these.
const FILTER_ORDER = [...courseLoadFilterNames].sort((a, b) => filterLabel(a).localeCompare(filterLabel(b)));

/** A filter's label in the bar: its menu's, or "Program", whose menu comes from the API. */
function filterLabel(name: CourseLoadFilterName): string {
  return name === "program" ? "Program" : courseLoadFilterMenus[name].label;
}

type FilterBarProps = {
  cohort: CohortLens;
  filters: CourseLoadFilters;
  onCohort: (value: CohortLens) => void;
  onChange: (name: CourseLoadFilterName, value: string) => void;
  onClear: () => void;
};

/** One compact row: the cohort and every student filter. Every chart except the equity gaps follows them. */
export function FilterBar({ cohort, filters, onCohort, onChange, onClear }: FilterBarProps) {
  const programs = usePrograms(cohort);

  const programLabels: Record<string, string> = {
    all: "All programs",
    none: "None recorded",
    ...Object.fromEntries(programs.map((program) => [program.code, program.label])),
  };
  // A program picked in another cohort stays selectable, even if this cohort has fewer than 10.
  const programValues = ["all", "none", ...programs.map((program) => program.code)];
  if (!programValues.includes(filters.program)) {
    programValues.push(filters.program);
    programLabels[filters.program] = filters.program;
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-9">
        <FilterSelect
          id="student-filter-cohort"
          label="Cohort"
          value={cohort}
          values={cohortLenses}
          labels={cohortLensLabels}
          onChange={onCohort}
          compact
        />
        {FILTER_ORDER.map((name) => {
          if (name === "program") {
            return (
              <FilterSelect
                key={name}
                id="student-filter-program"
                label="Program"
                value={filters.program}
                values={programValues}
                labels={programLabels}
                onChange={(value) => onChange("program", value)}
                compact
              />
            );
          }
          const menu = courseLoadFilterMenus[name];
          return (
            <FilterSelect
              key={name}
              id={`student-filter-${name}`}
              label={menu.label}
              value={filters[name]}
              values={menu.values}
              labels={menu.labels}
              onChange={(value) => onChange(name, value)}
              compact
            />
          );
        })}
      </div>
      {isFiltered(filters) && (
        <Button variant="ghost" size="sm" className="h-7 self-start px-2 text-xs" onClick={onClear}>
          <X className="size-3" aria-hidden />
          Clear filters
        </Button>
      )}
    </div>
  );
}

type Program = { code: string; label: string };

/** The programs the program filter offers in one cohort lens, or none while loading. */
function usePrograms(cohort: CohortLens): Program[] {
  const loadPrograms = useMemo(() => courseLoadProgramsLoader(cohort), [cohort]);
  const { resource } = useApiResource(loadPrograms);
  return resource.status === "success" ? resource.data : [];
}
