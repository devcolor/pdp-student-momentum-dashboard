/** The presidential view's cards a staff member can ask about, and what to suggest asking.
 *
 * A keyword carries the card's label, the cohort lens and the figures the page already drew, never a
 * sentence: the server checks each one and writes the sentences about the card itself.
 *
 * The suggestions are a fixed table, so opening the chat makes no model call. Enrollment and
 * Completion are not published measures, so their questions need no breakdown by group.
 */

import type { Schemas } from "@/lib/api/types";
import type { Kpi } from "@/lib/sandbox";

import { type CohortLens, cohortLensLabels } from "../executive-view/data";
import type { TrendRow } from "./data";

export type KeywordContext = Schemas["KeywordContext"];

type TrendPoint = Schemas["TrendPoint"];

// The most trend points the server takes, one per entering cohort.
const MAX_TREND_POINTS = 4;

// Each card's own question, keyed by the card label the server sends (student_success/results.py _TILES).
const CARD_QUESTIONS = new Map([
  ["Enrollment", "Which cohorts are only partly observed, and what does that mean for the other cards?"],
  ["Retention", "Which groups are furthest behind on retention?"],
  ["Persistence", "How does fall-to-spring persistence differ by race and by gender?"],
  ["Transfer out", "How does transfer out differ by race and by gender?"],
  ["Completion", "Why are the newest cohorts' completion points dashed, and what does that mean?"],
]);

/** One KPI card: its label, the lens, the value it shows, and its trend across cohorts, oldest first. */
export function fromPresidentialKpi(kpi: Kpi, cohort: CohortLens, trend: TrendRow[]): KeywordContext {
  // Enrollment counts students; the other cards are percents.
  const isCount = kpi.unit === "count";
  return {
    view: "presidential-view",
    kind: "measure",
    measure: kpi.label,
    cohort,
    rate: isCount ? null : kpi.value,
    n: isCount ? kpi.value : null,
    group: null,
    gap_pts: null,
    filtered: false,
    // The rows come oldest first; should there ever be more cohorts than the server takes, keep the newest.
    trend: trend.slice(-MAX_TREND_POINTS).map(toTrendPoint),
  };
}

/** One trend row as the chat takes it: the cohort, the value the line drew, and whether it was dashed. */
function toTrendPoint(row: TrendRow): TrendPoint {
  // The rows' cohorts are single entering years, which TrendRow types as any string.
  return { cohort: row.cohort as TrendPoint["cohort"], value: row.value, partial: row.partial };
}

/** What the panel says it is scoped to: the card, the lens and the page. */
export function scopeOf(keyword: KeywordContext): string {
  return `${keyword.measure} · ${cohortLensLabels[keyword.cohort as CohortLens]} · Presidential view`;
}

/** Four questions about one card, from a fixed table. */
export function suggestionsFor(keyword: KeywordContext): string[] {
  const label = keyword.measure ?? "";
  const cardQuestion = CARD_QUESTIONS.get(label);
  return [
    "Explain this number and how it moved across cohorts, in plain language.",
    `How is ${label} defined here, and which students does it count?`,
    ...(cardQuestion ? [cardQuestion] : []),
    "What should I keep in mind before comparing cohorts on this card?",
  ];
}
