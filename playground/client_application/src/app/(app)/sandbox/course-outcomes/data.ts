/** /sandbox/course-outcomes: DFW rate by course for everyone and for one group: a race, a gender, or both. */

import type { Paths, Schemas } from "@/lib/api/types";
import { type SearchParams, parseChoice } from "@/lib/routes";
import { sandboxLoader } from "@/lib/sandbox";

import {
  genderLabels as groupGenderLabels,
  genders as groupGenders,
  raceLabels as groupRaceLabels,
  races as groupRaces,
} from "../deaggregation/data";

/** The DFW endpoint's query params; the picker types come from them. */
type CoursesQuery = NonNullable<Paths["/api/v1/sandbox/course-outcomes/dfw"]["get"]["parameters"]["query"]>;

/** One race, or "all" for every race. */
export type RaceChoice = NonNullable<CoursesQuery["race"]>;
/** One gender, or "all" for every gender. */
export type GenderChoice = NonNullable<CoursesQuery["gender"]>;

// This page's own lists: "All" first, then the de-aggregation page's. satisfies keeps each a value the server accepts.
export const races = ["all", ...groupRaces] as const satisfies readonly RaceChoice[];
export const genders = ["all", ...groupGenders] as const satisfies readonly GenderChoice[];
export const raceLabels: Record<RaceChoice, string> = { all: "All races", ...groupRaceLabels };
export const genderLabels: Record<GenderChoice, string> = { all: "All genders", ...groupGenderLabels };

/** Whether the picks are All races and All genders: the group is everyone, so there is no difference to show. */
export function isEveryone(race: RaceChoice, gender: GenderChoice): boolean {
  return race === "all" && gender === "all";
}

export const minimums = ["50", "100", "200", "500"] as const;
export type Minimum = (typeof minimums)[number];
export const minimumLabels: Record<Minimum, string> = {
  "50": "50+ enrollments",
  "100": "100+ enrollments",
  "200": "200+ enrollments",
  "500": "500+ enrollments",
};

/** The values the pickers start on. Sort isn't a link param, so it always starts on widest difference. */
export type CoursePicks = { race: RaceChoice; gender: GenderChoice; minimum: Minimum };

/**
 * The pickers' starting values from a link's race, gender and min_enrollments params. A missing or unknown value
 * falls back to the default (African American men, 200+), so All needs an explicit race=all or gender=all.
 */
export function picksFromParams(params: SearchParams): CoursePicks {
  return {
    race: parseChoice(params.race, races, "Black or African American"),
    gender: parseChoice(params.gender, genders, "M"),
    minimum: parseChoice(params.min_enrollments, minimums, "200"),
  };
}

export type Sort = NonNullable<CoursesQuery["sort"]>;
export const sorts = ["difference", "group_dfw", "busiest"] as const satisfies readonly Sort[];
export const sortLabels: Record<Sort, string> = {
  difference: "Widest difference",
  group_dfw: "Highest DFW for the group",
  busiest: "Most enrollments",
};

/** The sorts the picker offers. With everyone as the group there is no difference, so widest difference goes. */
export function sortsFor(race: RaceChoice, gender: GenderChoice): readonly Sort[] {
  return isEveryone(race, gender) ? sorts.filter((sort) => sort !== "difference") : sorts;
}

/** The sort picker's labels. With everyone as the group there is no group, so its sort is just the highest DFW. */
export function sortLabelsFor(race: RaceChoice, gender: GenderChoice): Record<Sort, string> {
  return isEveryone(race, gender) ? { ...sortLabels, group_dfw: "Highest DFW" } : sortLabels;
}

/** The picked sort, or highest DFW when the picker doesn't offer it (the server orders everyone the same way for both). */
export function shownSort(sort: Sort, race: RaceChoice, gender: GenderChoice): Sort {
  return sortsFor(race, gender).includes(sort) ? sort : "group_dfw";
}

export type CourseRow = Schemas["CourseRow"];
export type Courses = Schemas["CourseResponse"];

/** /sandbox/course-outcomes/dfw: DFW by course for everyone and for the picked group. */
export function coursesLoader(race: RaceChoice, gender: GenderChoice, minimum: Minimum, sort: Sort) {
  const searchParams = new URLSearchParams({ race, gender, min_enrollments: minimum, sort });
  return sandboxLoader<Courses>(`/course-outcomes/dfw?${searchParams.toString()}`);
}

export type Comparison = Schemas["Comparison"];
export type MidtermAlerts = Schemas["MidtermAlertResponse"];

/** /sandbox/course-outcomes/midterm-alerts: the planted midterm stand-in for early alerts. */
export function midtermLoader(race: RaceChoice, gender: GenderChoice, minimum: Minimum) {
  const searchParams = new URLSearchParams({ race, gender, min_enrollments: minimum });
  return sandboxLoader<MidtermAlerts>(`/course-outcomes/midterm-alerts?${searchParams.toString()}`);
}
