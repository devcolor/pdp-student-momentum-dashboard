/** Every page address the client links to, so a renamed page is changed in one place. */
export const routes = {
  home: "/",
  workbench: "/workbench",
  workbenchUpload: "/workbench/upload",
  workbenchExplore: "/workbench/explore",
  workbenchFields: "/workbench/fields",
  sandbox: "/sandbox",
  sandboxChartExamples: "/sandbox/chart-examples",
  sandboxAppShell: "/sandbox/app-shell",
  sandboxDashboard: "/sandbox/dashboard",
  sandboxMeasures: "/sandbox/measures",
  sandboxEnrollmentTrends: "/sandbox/enrollment-trends",
  sandboxExecutiveView: "/sandbox/executive-view",
  sandboxStudentSuccess: "/sandbox/student-success",
  sandboxMvsuStudentSuccess: "/sandbox/mvsu-student-success",
  sandboxPresidentialView: "/sandbox/presidential-view",
  sandboxAidMomentum: "/sandbox/aid-momentum",
  sandboxDataChatUi: "/sandbox/data-chat-ui",
  sandboxKpiExamples: "/sandbox/kpi-examples",
  sandboxChatUi: "/sandbox/chat-ui",
  sandboxApiRequests: "/sandbox/api-requests",
  sandboxAddASandboxPage: "/sandbox/add-a-sandbox-page",
  sandboxDeaggregation: "/sandbox/deaggregation",
  sandboxCourseOutcomes: "/sandbox/course-outcomes",
  sandboxCredentialTrends: "/sandbox/credential-trends",
  sandboxAssociateMomentum: "/sandbox/associate-momentum",
} as const;

/** A page's query params, as Next.js hands them to a page. */
export type SearchParams = Record<string, string | string[] | undefined>;

/** The pages the data chat can link to; matches the server's PageLink.page. */
export type LinkPage = "deaggregation" | "course-outcomes" | "aid-momentum" | "student-success";

const linkPagePaths: Record<LinkPage, string> = {
  deaggregation: routes.sandboxDeaggregation,
  "course-outcomes": routes.sandboxCourseOutcomes,
  "aid-momentum": routes.sandboxAidMomentum,
  "student-success": routes.sandboxStudentSuccess,
};

/** Whether a page name from the server is one the client can link to. */
export function isLinkPage(page: string): page is LinkPage {
  return Object.hasOwn(linkPagePaths, page);
}

/** A same-origin path to a link page, with its picker values as query params. Empty values are left out. */
export function pageHref(page: LinkPage, params: Record<string, string> = {}): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== "") query.set(key, value);
  }
  const search = query.toString();
  return search ? `${linkPagePaths[page]}?${search}` : linkPagePaths[page];
}

/** A page's query param, if it is one of the allowed values; otherwise the fallback. A repeated param uses its first value. */
export function parseChoice<T extends string>(
  value: string | string[] | undefined,
  allowed: readonly T[],
  fallback: T,
): T {
  const first = Array.isArray(value) ? value[0] : value;
  return allowed.find((choice) => choice === first) ?? fallback;
}
