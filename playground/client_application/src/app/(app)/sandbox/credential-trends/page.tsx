import type { Metadata } from "next";

import { ViewHeader } from "@/components/sandbox/view-header";
import { SectionHeading } from "@/components/section-heading";

import { DriverChart, PathwayChart, ProgramChart, TrendChart } from "./charts";

export const metadata: Metadata = {
  title: "Sandbox Credential trends",
  description: "Are associate degrees falling and certificates rising? A same-clock comparison, then what moves it.",
};

const SECTIONS = [
  {
    id: "credential-trend-heading",
    title: "Is the trend real?",
    text: "Counted with no time limit, newer cohorts look worse only because they have had less time, and an associate takes two or more years. Switch to a fixed number of years to compare cohorts on the same clock.",
    chart: <TrendChart />,
  },
  {
    id: "credential-program-heading",
    title: "Which programs move the count?",
    text: "Certificate counts are lumpy: one program opening, closing or growing can look like a college-wide trend. Split by program before reading a trend.",
    chart: <ProgramChart />,
  },
  {
    id: "credential-pathway-heading",
    title: "Alongside the degree, or instead of it?",
    text: "For students who earned a credential: did a certificate come with the associate, as a built-in or stackable step, or in place of it?",
    chart: <PathwayChart />,
  },
  {
    id: "credential-driver-heading",
    title: "Who finishes?",
    text: "Among students who came for a credential, each group against everyone else. The gaps and the likely-noise flags come from the shared gap finder.",
    chart: <DriverChart />,
  },
];

/** The credential trends page: check the trend is real, then look for what moves it. */
export default function SandboxCredentialTrendsPage() {
  return (
    <>
      {/* Pulled up to sit where the dashboards' headers do. */}
      <ViewHeader
        title="Credential trends"
        question="Are associates falling, and certificates rising?"
        className="-mt-6 sm:-mt-10"
      >
        <p>
          Read the charts in order: first check the trend is real, then look for what moves it. Counts come from the
          loaded PDP data model. The data is synthetic, so nothing here is a finding about real students or
          institutions.
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
