import type { Metadata } from "next";
import { Suspense } from "react";

import { ViewHeader } from "@/components/sandbox/view-header";
import { Skeleton } from "@/components/ui/skeleton";
import type { SearchParams } from "@/lib/routes";

import { dimensionFromParams } from "./data";
import { SnapshotViews } from "./views";

export const metadata: Metadata = {
  title: "Sandbox Collegewide student success snapshot",
  description: "Enrollment, retention, persistence, transfer and completion, with the largest equity gaps.",
};

/** The snapshot, with the split-by picker starting on the dimension a link names (?dimension=). */
async function LinkedViews({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const dimension = dimensionFromParams(await searchParams);
  // A new key resets the pickers when a link to this page names a different dimension.
  return <SnapshotViews key={dimension} initialDimension={dimension} />;
}

/** The executive view's layout, led by the five student success KPIs. */
export default function SandboxStudentSuccessPage({ searchParams }: PageProps<"/sandbox/student-success">) {
  return (
    <div data-full-width className="-mt-6 -mb-16 flex flex-col gap-4 sm:-mt-10">
      <ViewHeader title="Collegewide student success snapshot">
        <p>
          Enrollment, retention, persistence, transfer and completion, with an equity analysis and a completion action
          board. Synthetic data, not findings about real students or institutions.
        </p>
      </ViewHeader>
      {/* The dimension is in the URL's query, known only when someone asks for the page. */}
      <Suspense fallback={<Skeleton className="h-96 rounded-xl" />}>
        <LinkedViews searchParams={searchParams} />
      </Suspense>
    </div>
  );
}
