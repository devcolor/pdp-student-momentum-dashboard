/** /sandbox/deaggregation: labels and formatting only. Every number comes from the server. */

import type { Gender, OutcomeRow, Rate } from "./data";

/** "Black or African American men". */
export function groupName(race: string, gender: Gender): string {
  return `${race} ${gender === "M" ? "men" : "women"}`;
}

/** The other gender of the same race, e.g. "Black or African American women". */
export function otherGroupName(race: string, gender: Gender): string {
  return groupName(race, gender === "M" ? "F" : "M");
}

/** −13.9 pts, with a real minus sign. */
export function formatPoints(value: number): string {
  const sign = value < 0 ? "−" : value > 0 ? "+" : "";
  return `${sign}${Math.abs(value).toFixed(1)} pts`;
}

/** "14.7% · n=190", or "Hidden" for a group under 10. */
export function formatRate(rate: Rate, counts: OutcomeRow["counts"]): string {
  if (rate.rate === null || rate.n === null) return "Hidden";
  const unit = counts === "enrollments" ? " enrollments" : "";
  return `${rate.rate}% · n=${rate.n.toLocaleString()}${unit}`;
}

/** The gap line under a measure: its size, interval and rank, or why it wasn't tested. */
export function gapSummary(row: OutcomeRow): string {
  if (row.not_tested) return row.not_tested;
  if (row.gap_pts === null || row.ci_low === null || row.ci_high === null) return "No comparison: the group is hidden.";
  const interval = `95% ${formatPoints(row.ci_low)} to ${formatPoints(row.ci_high)}`;
  const rank = row.rank !== null && row.ranked_of !== null ? ` · rank ${row.rank} of ${row.ranked_of}` : "";
  return `${formatPoints(row.gap_pts)} vs everyone else · ${interval}${rank}`;
}

/** Tested gaps that are behind and hold up after the noise check. */
export function realGapsBehind(rows: OutcomeRow[]): OutcomeRow[] {
  return rows.filter((row) => row.gap_pts !== null && row.gap_pts < 0 && row.likely_noise === false);
}
