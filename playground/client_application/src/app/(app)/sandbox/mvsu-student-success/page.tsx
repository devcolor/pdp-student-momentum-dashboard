import type { Metadata } from "next";

import { ViewHeader } from "@/components/sandbox/view-header";

import { SnapshotViews } from "../student-success/views";

export const metadata: Metadata = {
  title: "Sandbox MVSU student success snapshot",
  description: "Enrollment, retention, persistence, transfer and completion, with MVSU's equity analysis and action board.",
};

/** MVSU's version of the collegewide snapshot: no associate tile, and next-term gateway steps. */
export default function SandboxMvsuStudentSuccessPage() {
  return (
    <div data-full-width className="-mt-6 -mb-16 flex flex-col gap-4 sm:-mt-10">
      <ViewHeader title="Universitywide student success snapshot">
        <p>
          Enrollment, retention, persistence, transfer and completion, with cohort demographics and a completion action
          board. Synthetic data, not findings about real students or institutions.
        </p>
      </ViewHeader>
      <SnapshotViews school="mvsu" />
    </div>
  );
}
