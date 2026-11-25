import type { Metadata } from "next";

import { ViewHeader } from "@/components/sandbox/view-header";

import { CohortViews } from "./charts";

export const metadata: Metadata = {
  title: "Sandbox Executive view",
  description: "The headline success measures and the largest equity gaps on one page.",
};

/** The executive view, on one screen. The negative margins undo the sandbox layout's roomy padding. */
export default function SandboxExecutiveViewPage() {
  return (
    <div data-full-width className="-mt-6 -mb-16 flex flex-col gap-4 sm:-mt-10">
      <ViewHeader title="Executive view">
        <p>
          The headline success measures and the largest equity gaps on one page. Synthetic data, not findings about
          real students or institutions.
        </p>
      </ViewHeader>
      <CohortViews />
    </div>
  );
}
