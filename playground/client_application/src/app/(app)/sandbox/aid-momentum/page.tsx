import type { Metadata } from "next";
import { Suspense } from "react";

import { ViewHeader } from "@/components/sandbox/view-header";
import { Skeleton } from "@/components/ui/skeleton";
import type { SearchParams } from "@/lib/routes";

import { Charts } from "./charts";
import { measureFromParams } from "./data";

export const metadata: Metadata = {
  title: "Sandbox Unmet need and momentum",
  description: "Whether money, not ability, predicts who stalls, and what a Pell flag alone can tell you.",
};

/** The charts, with the picker starting on the measure a link names (?measure=). */
async function LinkedCharts({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const measure = measureFromParams(await searchParams);
  // A new key resets the picker when a link to this page names a different measure.
  return <Charts key={measure} initialMeasure={measure} />;
}

/** The unmet need page: one measure by need band, its ranked gaps, and Pell beside it. The negative margin undoes the sandbox layout's roomy top padding. */
export default function SandboxAidMomentumPage({ searchParams }: PageProps<"/sandbox/aid-momentum">) {
  return (
    <div data-full-width className="-mt-6 flex flex-col gap-4 sm:-mt-10">
      <ViewHeader title="Unmet need and momentum" question="Does money, not ability, predict who stalls?">
        <p>
          One measure by unmet need band, its ranked gaps, and what a Pell flag alone can tell you. The financial aid
          data is a synthetic stand-in with a planted effect, so nothing here is a finding about real students or
          institutions.
        </p>
      </ViewHeader>
      {/* The measure is in the URL's query, known only when someone asks for the page. */}
      <Suspense fallback={<Skeleton className="h-96 rounded-xl" />}>
        <LinkedCharts searchParams={searchParams} />
      </Suspense>
    </div>
  );
}
