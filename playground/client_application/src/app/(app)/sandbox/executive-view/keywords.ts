/** The things on this page a staff member can click to ask about, and what to suggest asking.
 *
 * A keyword carries names the page already rendered, never a sentence: the server checks each name
 * against what this view can show and writes the sentence itself.
 *
 * Every suggestion has to be answerable from the published measures, which bounds them. Published
 * are the student dimensions (race, gender, Pell, age, enrollment intensity, unmet need band,
 * affinity, educational goal), gender by race, and course for the course measures. There is no
 * program dimension, so "which programs" has no published answer and is not offered.
 */

import type { Schemas } from "@/lib/api/types";

import { type CohortLens, type CourseLoadFilters, cohortLensLabels, isFiltered } from "./data";

export type KeywordContext = Schemas["KeywordContext"];

type GapRow = Schemas["GapRow"];

// The tiles the chat can ground an answer in. Mirrors the server's allowed_measures(), which is
// the authority and refuses anything else. Graduation rate is deliberately absent: it comes from
// the institution's own records, so no published measure can answer a question about it.
const KEYWORD_MEASURES = new Set(["Retention", "Persistence elsewhere", "Gateway math", "Gateway English"]);

/** Whether a tile's label is a measure the chat can answer about. */
export function isKeywordMeasure(label: string): boolean {
  return KEYWORD_MEASURES.has(label);
}

/** A headline measure tile, such as Retention. A filtered tile is calculated live, so it says so. */
export function fromKpi(measure: string, cohort: CohortLens, filters: CourseLoadFilters, rate?: number): KeywordContext {
  return {
    kind: "measure",
    measure,
    cohort,
    rate: rate ?? null,
    group: null,
    gap_pts: null,
    n: null,
    filtered: isFiltered(filters),
    view: "executive-view",
  };
}

/** A measure heading over a list of gaps, such as the Gateway math column. Gaps are never filtered. */
export function fromMeasure(measure: string, cohort: CohortLens): KeywordContext {
  return { kind: "measure", measure, cohort, rate: null, group: null, gap_pts: null, n: null, filtered: false, view: "executive-view" };
}

/** One group that is behind on one measure, with the figures the page is showing for it. */
export function fromGap(measure: string, row: GapRow, cohort: CohortLens): KeywordContext {
  return {
    kind: "group",
    measure,
    group: row.group,
    cohort,
    rate: row.rate,
    gap_pts: row.gap_pts,
    n: row.n,
    filtered: false,
    view: "executive-view",
  };
}

/** The cohort the whole view is set to. */
export function fromCohort(cohort: CohortLens): KeywordContext {
  return { kind: "cohort", cohort, measure: null, group: null, rate: null, gap_pts: null, n: null, filtered: false, view: "executive-view" };
}

/** What the panel says it is scoped to, as a short line under its title. */
export function keywordLabel(keyword: KeywordContext): string {
  const where = keyword.cohort ? ` · ${cohortLensLabels[keyword.cohort as CohortLens]}` : "";
  if (keyword.kind === "group") return `${keyword.measure} · ${keyword.group}${where}`;
  if (keyword.kind === "measure") return `${keyword.measure}${where}`;
  return `All measures${where}`;
}

/** Four questions the published measures can answer about this keyword. */
export function suggestionsFor(keyword: KeywordContext): string[] {
  if (keyword.kind === "group") return groupSuggestions(keyword);
  if (keyword.kind === "measure") return measureSuggestions(keyword);
  return cohortSuggestions();
}

function groupSuggestions(keyword: KeywordContext): string[] {
  const measure = keyword.measure;
  const group = keyword.group;
  return [
    `How does ${measure} for ${group} compare with the other groups on the same breakdown?`,
    `Is the ${measure} gap for ${group} larger than the gaps by race or by gender?`,
    `What are the other published measures for ${group}?`,
    `Which other groups are behind on ${measure}?`,
  ];
}

function measureSuggestions(keyword: KeywordContext): string[] {
  const measure = keyword.measure;
  // Not "what is it overall": the tile already shows that figure, so the question invites a
  // pointless lookup.
  return [
    `How is ${measure} defined, and which students are left out of it?`,
    `Which groups are furthest behind on ${measure}?`,
    `Show ${measure} by race and by gender, and say which gaps stand out from noise.`,
    `Are any groups hidden on ${measure} because they are too small to show?`,
  ];
}

function cohortSuggestions(): string[] {
  return [
    "Which published measures do you have, and how is each one defined?",
    "Which gaps are the largest across all the measures?",
    "Which breakdowns are published, and which are not?",
    "Are any groups hidden because they are too small to show?",
  ];
}
