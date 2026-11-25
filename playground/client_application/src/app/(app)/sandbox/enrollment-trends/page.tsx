import type { Metadata } from "next";

import { ViewHeader } from "@/components/sandbox/view-header";

import { Charts } from "./charts";

export const metadata: Metadata = {
  title: "Sandbox Enrollment trends",
  description: "Who enters each cohort, and how each cohort carries forward term by term.",
};

/** The enrollment trends page: KPIs and both charts, from the loaded data model. The negative margin undoes the sandbox layout's roomy top padding. */
export default function SandboxEnrollmentTrendsPage() {
  return (
    <div data-full-width className="-mt-6 flex flex-col gap-4 sm:-mt-10">
      <ViewHeader title="Enrollment trends" question="Who enrolls, and who is still enrolled?">
        <p>
          Who enters each cohort, and how each cohort carries forward term by term. Synthetic data, not findings about
          real students or institutions.
        </p>
      </ViewHeader>
      <Charts />
    </div>
  );
}
