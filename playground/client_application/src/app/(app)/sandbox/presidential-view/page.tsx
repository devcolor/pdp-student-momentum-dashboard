import type { Metadata } from "next";

import { ViewHeader } from "@/components/sandbox/view-header";

import { PresidentialViews } from "./charts";

export const metadata: Metadata = {
  title: "Sandbox Presidential view",
  description: "Enrollment, retention, persistence, transfer and completion, with each metric's trend across cohorts.",
};

/** The presidential view: the five student success metrics now, and how they have moved. */
export default function SandboxPresidentialViewPage() {
  return (
    <div data-full-width className="-mt-6 -mb-16 flex flex-col gap-4 sm:-mt-10">
      <ViewHeader title="Presidential view">
        <p>
          Five student success metrics and their trends across entering cohorts. Synthetic data, not findings about
          real students or institutions.
        </p>
      </ViewHeader>
      <PresidentialViews />
    </div>
  );
}
