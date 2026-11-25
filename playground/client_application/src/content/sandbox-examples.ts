/** The sandbox's links, in the left sidebar and on /sandbox. Add an entry here and a new page appears in both. */

import {
  BookOpenCheck,
  ChartColumnBig,
  FilePlus2,
  Gauge,
  GraduationCap,
  LayoutDashboard,
  ListFilter,
  type LucideIcon,
  MessageCircle,
  Milestone,
  PanelsTopLeft,
  Presentation,
  PiggyBank,
  Send,
  Sparkles,
  TrendingUp,
  UsersRound,
} from "lucide-react";

import { routes } from "@/lib/routes";
import type { UniversityId } from "@/lib/theme";

export type SandboxExample = {
  label: string;
  /** One sentence for the card on /sandbox. */
  description: string;
  href: string;
  icon: LucideIcon;
};

export const SANDBOX_EXAMPLES_HEADING = "Sandbox Examples";

export const addYourOwnExample: SandboxExample = {
  label: "Add a Sandbox Example",
  description: "A worked example of adding a page with its own endpoints and charts.",
  href: routes.sandboxAddASandboxPage,
  icon: FilePlus2,
};

/** Add new examples to the end of this list. */
export const sandboxExamples: SandboxExample[] = [
  { label: "Charts", description: "Example charts, all served by one mock-data endpoint.", href: routes.sandboxChartExamples, icon: ChartColumnBig },
  { label: "App Shell", description: "The app shell's styles, each with its own address.", href: routes.sandboxAppShell, icon: PanelsTopLeft },
  { label: "Dashboard", description: "The example charts in a full-screen shell, with navigation and a context panel.", href: routes.sandboxDashboard, icon: LayoutDashboard },
  { label: "Chat UI", description: "Two chat layouts to start from, both with canned mock replies.", href: routes.sandboxChatUi, icon: MessageCircle },
  { label: "Measures", description: "A PDP-style example with typed filters and display-safe rates.", href: routes.sandboxMeasures, icon: ListFilter },
  { label: "API requests", description: "Live requests to the server application.", href: routes.sandboxApiRequests, icon: Send },
  { label: "KPI Examples", description: "KPI cards for percentages, splits and terms.", href: routes.sandboxKpiExamples, icon: Gauge },
  { label: "Chat UI: LLM over data", description: "The side-panel chat, answered by an LLM from the data model's definitions and aggregate queries.", href: routes.sandboxDataChatUi, icon: Sparkles },
];

/** Pages built on the loaded data model, listed in their own section at the top of the left sidebar. */
export const proofOfConceptItems: SandboxExample[] = [
  { label: "Enrollment trends", description: "Who enters each cohort, and how each cohort carries forward term by term.", href: routes.sandboxEnrollmentTrends, icon: TrendingUp },
  { label: "Credential trends", description: "Are associates falling and certificates rising? Compare cohorts on the same clock, then see what moves it.", href: routes.sandboxCredentialTrends, icon: GraduationCap },
  { label: "Associate momentum", description: "Where do associate-seekers stall? Credit milestones, near-completers and year-1 momentum.", href: routes.sandboxAssociateMomentum, icon: Milestone },
  { label: "De-aggregation", description: "One race × gender group across every success measure, from the saved results.", href: routes.sandboxDeaggregation, icon: UsersRound },
  { label: "Course outcomes", description: "DFW rate by course for one race × gender group, against everyone in the course.", href: routes.sandboxCourseOutcomes, icon: BookOpenCheck },
  { label: "Executive view", description: "The headline success measures and the largest equity gaps on one page.", href: routes.sandboxExecutiveView, icon: Presentation },
  { label: "Collegewide student success snapshot", description: "Enrollment, retention, persistence, transfer and completion, with an equity analysis and a completion action board.", href: routes.sandboxStudentSuccess, icon: Gauge },
  { label: "Universitywide student success snapshot", description: "MVSU's snapshot: the same metrics, cohort demographics, and a completion action board with next-term gateway steps.", href: routes.sandboxMvsuStudentSuccess, icon: Gauge },
  { label: "Presidential view", description: "Enrollment, retention, persistence, transfer and completion, with each metric's trend across cohorts.", href: routes.sandboxPresidentialView, icon: TrendingUp },
  { label: "Unmet need and momentum", description: "One measure by unmet need band, its ranked gaps, and what a Pell flag alone can tell you.", href: routes.sandboxAidMomentum, icon: PiggyBank },
];

/** Pick proof-of-concept pages by href, in the order given. */
function pickByHref(hrefs: string[]): SandboxExample[] {
  return hrefs.flatMap((href) => proofOfConceptItems.filter((item) => item.href === href));
}

/** The leading pages first, then every other proof-of-concept page in its usual order. */
function leadingThenRest(leadingHrefs: string[]): SandboxExample[] {
  const rest = proofOfConceptItems.filter((item) => !leadingHrefs.includes(item.href));
  return [...pickByHref(leadingHrefs), ...rest];
}

export const CCAC_VIEWS_HEADING = "CCAC Views";

/** CCAC's sidebar section: its four headline pages, then the rest, without MVSU's own snapshot. */
export const ccacViewItems: SandboxExample[] = leadingThenRest([
  routes.sandboxStudentSuccess,
  routes.sandboxPresidentialView,
  routes.sandboxAssociateMomentum,
  routes.sandboxDeaggregation,
]).filter((item) => item.href !== routes.sandboxMvsuStudentSuccess);

export const MVSU_VIEWS_HEADING = "MVSU Views";

const mvsuLeadingHrefs: string[] = [
  routes.sandboxPresidentialView,
  routes.sandboxExecutiveView,
  routes.sandboxEnrollmentTrends,
  routes.sandboxMvsuStudentSuccess,
  routes.sandboxDeaggregation,
  routes.sandboxCourseOutcomes,
];

// Hidden under MVSU; the pages still exist and stay under CCAC. MVSU has its own snapshot.
const mvsuHiddenHrefs: string[] = [routes.sandboxAssociateMomentum, routes.sandboxCredentialTrends, routes.sandboxStudentSuccess];

/** MVSU's sidebar section: its six headline pages, in order. */
export const mvsuViewItems: SandboxExample[] = pickByHref(mvsuLeadingHrefs);

export const MVSU_OTHER_VIEWS_HEADING = "Other Views";

/** MVSU's "Other Views" section: every proof-of-concept page not listed or hidden above. */
export const mvsuOtherViewItems: SandboxExample[] = proofOfConceptItems.filter(
  (item) => !mvsuLeadingHrefs.includes(item.href) && !mvsuHiddenHrefs.includes(item.href),
);

/** One section of a university's views, as the sidebar and the landing page both show it. */
export type ViewSection = { heading: string; items: SandboxExample[]; defaultOpen: boolean };

/** The sections for a university, in sidebar order; under dev/color or no pick, both. */
export function viewSectionsFor(university: UniversityId | null): ViewSection[] {
  const ccac: ViewSection[] = [{ heading: CCAC_VIEWS_HEADING, items: ccacViewItems, defaultOpen: true }];
  const mvsu: ViewSection[] = [
    { heading: MVSU_VIEWS_HEADING, items: mvsuViewItems, defaultOpen: true },
    { heading: MVSU_OTHER_VIEWS_HEADING, items: mvsuOtherViewItems, defaultOpen: false },
  ];
  if (university === "ccac") return ccac;
  if (university === "mvsu") return mvsu;
  return [...ccac, ...mvsu];
}

/** Where the landing page's "Get started" button goes for each pick: that pick's top page. */
export function startPageFor(university: UniversityId | null): string {
  if (university === "mvsu") return routes.sandboxPresidentialView;
  return routes.sandboxStudentSuccess;
}

export const ALL_VIEWS_HEADING = "All Views";

/** The landing page's cards: under dev/color, one card with every page; otherwise the side menu's sections. */
export function landingSectionsFor(university: UniversityId | null): ViewSection[] {
  if (university !== "devcolor") return viewSectionsFor(university);
  const items = viewSectionsFor(null).flatMap((section) => section.items);
  // A page can sit in more than one university's list; show it once.
  const unique = items.filter((item, index) => items.findIndex((other) => other.href === item.href) === index);
  return [{ heading: ALL_VIEWS_HEADING, items: unique, defaultOpen: true }];
}

/** Landing page groups inside each view card. A page sits in the first role that lists it; unlisted pages go last. */
const ROLES: { label: string; hrefs: string[] }[] = [
  {
    label: "For Executives",
    hrefs: [routes.sandboxPresidentialView, routes.sandboxExecutiveView, routes.sandboxEnrollmentTrends, routes.sandboxCredentialTrends],
  },
  { label: "For Faculty", hrefs: [routes.sandboxCourseOutcomes, routes.sandboxDeaggregation] },
  {
    label: "Student Deep-dive",
    hrefs: [routes.sandboxStudentSuccess, routes.sandboxMvsuStudentSuccess, routes.sandboxAssociateMomentum, routes.sandboxAidMomentum],
  },
];

export type RoleGroup = { label: string; items: SandboxExample[] };

/** Splits a section's pages by role, keeping their menu order and dropping empty roles. */
export function groupByRole(items: SandboxExample[]): RoleGroup[] {
  const groups: RoleGroup[] = ROLES.map((role) => ({
    label: role.label,
    items: items.filter((item) => role.hrefs.includes(item.href)),
  }));
  const listed = ROLES.flatMap((role) => role.hrefs);
  groups.push({ label: "Other", items: items.filter((item) => !listed.includes(item.href)) });
  return groups.filter((group) => group.items.length > 0);
}

/** Every example plus "Add a Sandbox Example", which stays last however many entries teams add above. */
export const sandboxNavItems: SandboxExample[] = [...sandboxExamples, addYourOwnExample];
