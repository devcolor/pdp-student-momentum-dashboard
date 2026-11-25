import { cn } from "@/lib/utils";

type PinnedFiltersProps = { children: React.ReactNode; className?: string };

/**
 * A page's filters, pinned to the top while the page scrolls under them, from md screens up. On a
 * phone the filters wrap to several rows, so pinned they'd cover the page; there they scroll away.
 * Put it directly in a column that holds the rest of the page, or it stops at that column's end.
 */
export function PinnedFilters({ children, className }: PinnedFiltersProps) {
  return <div className={cn("z-10 border-b bg-background py-2 md:sticky md:top-0", className)}>{children}</div>;
}
