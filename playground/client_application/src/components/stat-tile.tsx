import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "cn";

// chart-surface: KPIs are data, so like charts they ignore the UI theme.
const statTileClasses = "chart-surface flex h-full min-h-32 flex-col gap-1 rounded-2xl border bg-background p-4 text-foreground sm:p-5";

type StatTileProps = {
  /** The headline number, already formatted, e.g. "10,313". */
  value: React.ReactNode;
  /** A short unit after the number, e.g. "%". */
  unit?: string | null;
  /** Drawn right under the number, e.g. a change from last period. */
  trend?: React.ReactNode;
  label: React.ReactNode;
  /** Puts the label above the number instead of below it. */
  labelOnTop?: boolean;
  detail?: React.ReactNode;
  /** Drawn at the bottom of the tile, e.g. a small trend chart. */
  footer?: React.ReactNode;
  className?: string;
};

/** One big number with what it counts underneath. Wrap tiles in a list when there are several. */
export function StatTile({ value, unit, trend, label, labelOnTop = false, detail, footer, className }: StatTileProps) {
  const labelLine = <p className="text-sm leading-snug font-medium">{label}</p>;

  return (
    <div data-slot="stat-tile" className={cn(statTileClasses, className)}>
      {labelOnTop && labelLine}
      <p className="text-3xl font-semibold tracking-tight tabular-nums sm:text-4xl">
        {value}
        {unit && <span className="ml-1 text-base font-normal text-muted-foreground">{unit}</span>}
      </p>
      {trend}
      {!labelOnTop && labelLine}
      {detail && <p className="text-xs text-muted-foreground">{detail}</p>}
      {footer && <div className="mt-auto pt-2">{footer}</div>}
    </div>
  );
}

/** A StatTile-sized placeholder while the numbers load. */
export function StatTileSkeleton({ className }: { className?: string }) {
  return (
    <div data-slot="stat-tile-skeleton" className={cn(statTileClasses, className)}>
      <Skeleton className="h-full rounded-lg" />
    </div>
  );
}
