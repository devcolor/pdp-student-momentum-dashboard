"use client";

import type { ReactElement, ReactNode } from "react";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { ChartMeta, Kpi } from "@/lib/sandbox";

type DefinitionTooltipProps = {
  /** What the measure counts, from the server's meta.definitions. Nothing shows without one. */
  definition?: string;
  /** The name on the page. It becomes the trigger itself, so no extra element wraps it. */
  children: ReactElement;
};

/**
 * Explains a measure's name on hover and on keyboard focus.
 *
 * The name is often a button already, so the trigger renders as the child rather than wrapping it:
 * a button inside a button is invalid and breaks the click.
 */
export function DefinitionTooltip({
  definition,
  children,
}: DefinitionTooltipProps) {
  if (!definition) return children;

  return (
    <Tooltip>
      <TooltipTrigger render={children} />
      <TooltipContent className="max-w-xs text-pretty">
        {definition}
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * A KpiGrid renderLabel that explains a tile from the response's own definitions.
 *
 * Pass it to any KpiGrid: the root layout already provides the tooltip context. A tile with no
 * definition is drawn plainly, so a page can adopt this before every tile has one.
 */
export function explainKpiLabel(kpi: Kpi, meta: ChartMeta): ReactNode {
  const definition = meta.definitions?.[kpi.label];
  return (
    <DefinitionTooltip definition={definition}>
      <span
        className={
          definition
            ? "underline decoration-dotted underline-offset-4"
            : undefined
        }
      >
        {kpi.label}
      </span>
    </DefinitionTooltip>
  );
}
