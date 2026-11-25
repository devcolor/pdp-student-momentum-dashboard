"use client";

import { cn } from "@/lib/utils";

type FilterSelectProps<Value extends string> = {
  id: string;
  label: string;
  value: Value;
  values: readonly Value[];
  labels: Record<Value, string>;
  onChange: (value: Value) => void;
  /** Smaller label and box, for a dense filter bar. */
  compact?: boolean;
};

/** A labelled dropdown over a fixed list of typed filter values. */
export function FilterSelect<Value extends string>({ id, label, value, values, labels, onChange, compact = false }: FilterSelectProps<Value>) {
  return (
    <label className={cn("flex min-w-0 flex-col font-medium", compact ? "gap-1 text-xs" : "gap-2 text-sm")} htmlFor={id}>
      {label}
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value as Value)}
        className={cn(
          "w-full min-w-0 rounded-md border bg-background font-normal shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
          compact ? "h-8 px-2 text-xs" : "h-10 px-3 text-sm",
        )}
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
