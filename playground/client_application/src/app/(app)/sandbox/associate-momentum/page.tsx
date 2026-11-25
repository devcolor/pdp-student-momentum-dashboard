import type { Metadata } from "next";

import { ViewHeader } from "@/components/sandbox/view-header";
import { SectionHeading } from "@/components/section-heading";

import { MilestoneChart, NearCompleterChart, YearOneChart } from "./charts";

export const metadata: Metadata = {
  title: "Sandbox Associate momentum",
  description: "Where do associate-seekers stall? Credit milestones, near-completers and year-1 momentum.",
};

const SECTIONS = [
  {
    id: "momentum-milestones-heading",
    title: "Where do they drop off?",
    text: "Credits earned here, counted to fixed milestones on the same clock for every cohort. A credit total isn't a degree audit, and 60 credits for an associate is an assumption, so read the steps between the bars, not one bar alone.",
    chart: <MilestoneChart />,
  },
  {
    id: "momentum-near-heading",
    title: "Who is close but not done?",
    text: "Near-completers have most of the credits an associate takes but no credential yet. Those who stopped enrolling are the ones an advisor could call back. The brackets follow the repository's near-completers guide.",
    chart: <NearCompleterChart />,
  },
  {
    id: "momentum-year-one-heading",
    title: "Does a strong first year pay off?",
    text: "The associate within the window, by credits earned in year 1. Each band is compared with every other associate-seeker through the shared gap finder. A gap shows a difference, not its cause.",
    chart: <YearOneChart />,
  },
];

/** The associate momentum page: where students who came for an associate slow down. */
export default function SandboxAssociateMomentumPage() {
  return (
    <>
      {/* Pulled up to sit where the dashboards' headers do. */}
      <ViewHeader
        title="Associate momentum"
        question="Where do associate-seekers stall?"
        className="-mt-6 sm:-mt-10"
      >
        <p>
          Follow students who came for an associate degree: which credit milestones they reach, how many get close
          without finishing, and how much the first year predicts. Counts come from the loaded PDP data model. The data
          is synthetic, so nothing here is a finding about real students or institutions.
        </p>
      </ViewHeader>

      {SECTIONS.map((section) => (
        <section key={section.id} aria-labelledby={section.id} className="flex max-w-4xl flex-col gap-6">
          <SectionHeading id={section.id} title={section.title}>
            <p className="text-muted-foreground">{section.text}</p>
          </SectionHeading>
          {section.chart}
        </section>
      ))}
    </>
  );
}
