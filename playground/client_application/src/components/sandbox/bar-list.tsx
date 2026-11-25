import { type BarListItem, barWidthPercent } from "@/lib/charts";

type BarListProps = {
  items: BarListItem[];
  max?: number;
  /** Marks a value on every bar, e.g. all students, so each reads as above or below it. */
  reference?: number;
  /** A CSS color for every solid bar. Leave it out for the first chart color. */
  color?: string;
  /** Wraps each bar's label, e.g. to make it open a chat. Leave it out for plain text. */
  renderLabel?: (label: string) => React.ReactNode;
};

/** Horizontal bars with the value on the right, as in the briefs' "by student group" panels. */
export function BarList({ items, max = 100, reference, color, renderLabel }: BarListProps) {
  return (
    <ul className="flex flex-col gap-3.5">
      {items.map((item) => (
        <li key={item.label} className="flex flex-col gap-1.5">
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span>
              {renderLabel ? renderLabel(item.label) : item.label}
              {item.note && <span className="ml-2 text-xs text-muted-foreground">{item.note}</span>}
            </span>
            <span className="font-semibold tabular-nums">{item.display}</span>
          </div>
          <div className="relative">
            <div className="h-2 overflow-hidden rounded-full bg-muted" role="presentation">
              {item.segments ? (
                <div
                  className="flex h-full gap-px overflow-hidden rounded-full transition-[width] duration-700"
                  style={{ width: `${barWidthPercent(item.value, max)}%` }}
                >
                  {item.segments.map((segment) => (
                    <div
                      key={segment.key}
                      title={segment.title}
                      className="h-full basis-0"
                      style={{ flexGrow: segment.value, background: segment.color }}
                    />
                  ))}
                </div>
              ) : (
                <div
                  className="h-full rounded-full bg-chart-1 transition-[width] duration-700"
                  style={{ width: `${barWidthPercent(item.value, max)}%`, background: color }}
                />
              )}
            </div>
            {reference !== undefined && (
              <span
                aria-hidden
                className="absolute -top-0.5 h-3 w-0.5 -translate-x-1/2 rounded-full bg-foreground ring-2 ring-card"
                style={{ left: `${barWidthPercent(reference, max)}%` }}
              />
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
