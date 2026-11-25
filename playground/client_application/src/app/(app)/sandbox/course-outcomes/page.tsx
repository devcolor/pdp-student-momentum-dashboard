import type { Metadata } from "next";
import { Suspense } from "react";

import { ViewHeader } from "@/components/sandbox/view-header";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import type { SearchParams } from "@/lib/routes";

import { Charts } from "./charts";
import { picksFromParams } from "./data";

export const metadata: Metadata = {
  title: "Sandbox Course Outcomes",
  description:
    "DFW rate and planted midterm alerts by course for a race × gender group (either can be All), against everyone in the course.",
};

/** The charts, with the pickers starting on the values a link names (?race=&gender=&min_enrollments=). */
async function LinkedCharts({ searchParams, midtermIntro }: { searchParams: Promise<SearchParams>; midtermIntro: React.ReactNode }) {
  const initial = picksFromParams(await searchParams);
  // A new key resets the pickers when a link to this page names different values.
  return <Charts key={`${initial.race}|${initial.gender}|${initial.minimum}`} initial={initial} midtermIntro={midtermIntro} />;
}

/** The course outcomes page: DFW and planted midterm alerts by course for a race x gender group, a race, a gender or everyone. */
export default function SandboxCourseOutcomesPage({ searchParams }: PageProps<"/sandbox/course-outcomes">) {
  return (
    <>
      {/* Pulled up to sit where the dashboards' headers do. */}
      <ViewHeader
        title="Course outcomes"
        question="In which courses does a group's DFW rate run highest?"
        className="-mt-6 sm:-mt-10"
      >
        <p>
          The shared DFW measure by course, for one race × gender group against everyone who took the same
          course. Pick All races or All genders to compare one race or one gender, or both to see everyone alone.
          Counts are course enrollments, and differences aren&apos;t tested for noise. The data is synthetic: nothing
          on this page is a finding about CCAC students.
        </p>
      </ViewHeader>

      <section aria-labelledby="course-outcomes-heading" className="flex flex-col gap-6">
        <SectionHeading id="course-outcomes-heading" title="DFW by course">
          <p className="text-muted-foreground">
            Most groups are small within one course, so many are hidden. Lower the course size to see more, and
            read small groups with care.
          </p>
        </SectionHeading>
        {/* The pickers' starting values are in the URL's query, known only when someone asks for the page. */}
        <Suspense fallback={<Skeleton className="h-96 max-w-4xl rounded-xl" />}>
          <LinkedCharts
            searchParams={searchParams}
            midtermIntro={
              <p className="text-muted-foreground">
                No early-alert data is loaded yet, so midterm grades stand in: an alert is a midterm D or L (failing).
                This card is synthetic and planted. The midterms were generated from the final grades, so their link
                to DFW is circular by construction, and with no intervention data, recovery says nothing about whether
                alerts work. Real early-alert data replaces it once it&apos;s loaded. The pickers above
                drive this card too; it is always sorted by widest difference, or by highest alert rate for everyone.
              </p>
            }
          />
        </Suspense>
      </section>
    </>
  );
}
