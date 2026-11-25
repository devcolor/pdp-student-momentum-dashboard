import type { Schemas } from "@/lib/api/types";
import { type SearchParams, parseChoice } from "@/lib/routes";
import { sandboxLoader } from "@/lib/sandbox";

/** /sandbox/deaggregation: one race x gender group across every success measure. */
export type Rate = Schemas["Rate"];
export type OutcomeRow = Schemas["OutcomeRow"];
export type Outcomes = Schemas["OutcomeResponse"];
export type Race = Outcomes["race"];
export type Gender = Outcomes["gender"];

// Picker order; satisfies keeps each entry a race the server accepts.
export const races = [
  "Black or African American",
  "American Indian or Alaska Native",
  "Asian",
  "Hispanic",
  "Native Hawaiian or Other Pacific Islander",
  "Nonresident alien",
  "Two or More Races",
  "White",
] as const satisfies readonly Race[];

export const genders = ["M", "F"] as const satisfies readonly Gender[];

export const raceLabels = Object.fromEntries(races.map((race) => [race, race])) as Record<Race, string>;
export const genderLabels: Record<Gender, string> = { M: "Men", F: "Women" };

/** The group the pickers start on. */
export type GroupPicks = { race: Race; gender: Gender };

/** The group the pickers start on from a link's race and gender params; an unknown value falls back to African American men. */
export function groupFromParams(params: SearchParams): GroupPicks {
  return {
    race: parseChoice(params.race, races, "Black or African American"),
    gender: parseChoice(params.gender, genders, "M"),
  };
}

/** Loads every measure for one race x gender group. */
export function outcomesLoader(race: Race, gender: Gender) {
  const searchParams = new URLSearchParams({ race, gender });
  return sandboxLoader<Outcomes>(`/deaggregation/outcomes?${searchParams.toString()}`);
}
