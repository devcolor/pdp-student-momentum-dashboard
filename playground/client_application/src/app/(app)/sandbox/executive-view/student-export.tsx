"use client";

import { Download } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { type CohortLens, type CourseLoadFilters, type ExportMeasure, exportMeasures, studentExportUrl } from "./data";

type ExportProps = { cohort: CohortLens; filters: CourseLoadFilters };

/** Downloads every matching student's ID with a Yes, No or blank for each headline measure. */
export function ExportAllButton({ cohort, filters }: ExportProps) {
  return (
    <a
      href={studentExportUrl(cohort, filters)}
      download
      className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
    >
      <Download className="size-4" aria-hidden />
      Export student IDs
    </a>
  );
}

/** A tile's own export: the students that measure counts, with its Yes or No. Nothing for other tiles. */
export function ExportTileLink({ cohort, filters, kpiId }: ExportProps & { kpiId: string }) {
  const measure = exportMeasures.find((name) => name === kpiId) as ExportMeasure | undefined;
  if (!measure) return null;
  return (
    <a
      href={studentExportUrl(cohort, filters, measure)}
      download
      className="inline-flex w-fit items-center gap-1 text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
    >
      <Download className="size-3.5" aria-hidden />
      Export IDs
    </a>
  );
}
