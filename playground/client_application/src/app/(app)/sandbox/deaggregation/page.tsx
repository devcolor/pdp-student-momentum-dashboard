import type { Metadata } from "next";
import { Suspense } from "react";

import { ViewHeader } from "@/components/sandbox/view-header";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import type { SearchParams } from "@/lib/routes";

import { Charts } from "./charts";
import { groupFromParams } from "./data";

export const metadata: Metadata = {
  title: "Sandbox De-aggregation",
  description: "One race × gender group across every success measure, starting with African American men.",
};

/** The charts, with the pickers starting on the group a link names (?race=&gender=). */
async function LinkedCharts({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const initial = groupFromParams(await searchParams);
  // A new key resets the pickers when a link to this page names a different group.
  return <Charts key={`${initial.race}|${initial.gender}`} initial={initial} />;
}

/** The de-aggregation page: one race x gender group across every success measure. */
export default function SandboxDeaggregationPage({ searchParams }: PageProps<"/sandbox/deaggregation">) {
  return (
    <>
      {/* Pulled up to sit where the dashboards' headers do. */}
      <ViewHeader
        title="De-aggregation"
        question="Where do African American men fall behind?"
        className="-mt-6 sm:-mt-10"
      >
        <p>
          Each measure for one race × gender group, beside the other gender of the same race and everyone. The rates
          come from the shared measures and the gaps from the gap finder; nothing is recomputed here. The
          data is synthetic: nothing on this page is a finding about CCAC students.
        </p>
      </ViewHeader>

      <section aria-labelledby="deaggregation-result-heading" className="flex flex-col gap-6">
        <SectionHeading id="deaggregation-result-heading" title="Measure by measure">
          <p className="text-muted-foreground">
            Gateway courses and first-term checks come first, then the rest of year 1, retention and persistence. A
            gap is tested only for yes-or-no measures; faded lines are likely noise.
          </p>
        </SectionHeading>
        {/* The group is in the URL's query, known only when someone asks for the page. */}
        <Suspense fallback={<Skeleton className="h-96 max-w-4xl rounded-xl" />}>
          <LinkedCharts searchParams={searchParams} />
        </Suspense>
      </section>
    </>
  );
}
