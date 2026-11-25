"use client";

import { useMemo, useState } from "react";

import { ChatPageContext } from "@/components/chat/chat-page-context";
import { ChartCard } from "@/components/sandbox/chart-card";
import { FilterSelect } from "@/components/sandbox/filter-select";
import { PinnedFilters } from "@/components/sandbox/pinned-filters";
import { SectionHeading } from "@/components/section-heading";
import { StatTile } from "@/components/stat-tile";
import { seriesColor } from "@/lib/charts";

import { formatPoints } from "../deaggregation/chart-config";
import type { Rate } from "../deaggregation/data";
import {
  type Comparison,
  type CoursePicks,
  type CourseRow,
  type Courses,
  type GenderChoice,
  type MidtermAlerts,
  type Minimum,
  type RaceChoice,
  type Sort,
  coursesLoader,
  genderLabels,
  genders,
  isEveryone,
  midtermLoader,
  minimumLabels,
  minimums,
  raceLabels,
  races,
  shownSort,
  sortLabelsFor,
  sortsFor,
} from "./data";

/** Bar colours from the chosen chart palette; everyone stays neutral so the groups stand out. */
const GROUP_COLOR = seriesColor(0);
const EVERYONE_COLOR = "color-mix(in oklab, var(--foreground) 40%, transparent)";

/**
 * Pick a group and a course size, then read the busy courses where the group's DFW rate is worst,
 * and the planted midterm alerts for the same group and courses. `initial` comes from the page's link.
 * All races and All genders together make the group everyone, so each course gets one bar.
 */
export function Charts({ initial, midtermIntro }: { initial: CoursePicks; midtermIntro?: React.ReactNode }) {
  const [race, setRace] = useState<RaceChoice>(initial.race);
  const [gender, setGender] = useState<GenderChoice>(initial.gender);
  const [minimum, setMinimum] = useState<Minimum>(initial.minimum);
  const [sort, setSort] = useState<Sort>("difference");
  // Derived, not stored: widest difference comes back once a group is picked again.
  const sortShown = shownSort(sort, race, gender);
  const load = useMemo(() => coursesLoader(race, gender, minimum, sortShown), [race, gender, minimum, sortShown]);
  const loadMidterms = useMemo(() => midtermLoader(race, gender, minimum), [race, gender, minimum]);

  return (
    <div className="flex max-w-4xl flex-col gap-4">
      <PinnedFilters>
        <div className="grid gap-4 sm:grid-cols-4">
          <FilterSelect id="minimum" label="Courses" value={minimum} values={minimums} labels={minimumLabels} onChange={setMinimum} />
          <FilterSelect id="gender" label="Gender" value={gender} values={genders} labels={genderLabels} onChange={setGender} />
          <FilterSelect id="race" label="Race" value={race} values={races} labels={raceLabels} onChange={setRace} />
          <FilterSelect id="sort" label="Sort" value={sortShown} values={sortsFor(race, gender)} labels={sortLabelsFor(race, gender)} onChange={setSort} />
        </div>
      </PinnedFilters>

      <ChartCard id="course-dfw" load={load}>
        {(data) => (
          <div className="flex flex-col gap-8">
            <ChatPageContext page={{ title: data.meta.title, filters: data.meta.filters, specs: data.meta.specs }} />
            <Headlines data={data} />
            <Legend name={isEveryone(data.race, data.gender) ? null : data.group_label} />
            <ul className="flex flex-col gap-5">
              {data.rows.map((row) => (
                <CourseLine key={row.course} row={row} everyone={isEveryone(data.race, data.gender)} />
              ))}
            </ul>
          </div>
        )}
      </ChartCard>

      <section aria-labelledby="midterm-alerts-heading" className="mt-6 flex flex-col gap-4">
        <SectionHeading id="midterm-alerts-heading" title="Early alerts: a planted stand-in">
          {midtermIntro}
        </SectionHeading>
        <ChartCard id="course-midterms" load={loadMidterms}>
          {(data) => (
            <div className="flex flex-col gap-8">
              <MidtermHeadlines data={data} />
              <Legend name={isEveryone(data.race, data.gender) ? null : data.group_label} />
              <ul className="flex flex-col gap-5">
                {data.rows.map((row) => (
                  <CourseLine key={row.course} row={row} everyone={isEveryone(data.race, data.gender)} />
                ))}
              </ul>
            </div>
          )}
        </ChartCard>
      </section>
    </div>
  );
}

/** The group's midterm alert and recovery rates across all courses, and how many courses show it. */
function MidtermHeadlines({ data }: { data: MidtermAlerts }) {
  const everyone = isEveryone(data.race, data.gender);
  const shown = data.courses_considered - data.courses_with_group_hidden;
  const detail = `${data.min_enrollments}+ enrollments with a midterm`;
  return (
    <ul className="grid gap-3 sm:grid-cols-3">
      <li>
        <ComparisonTile comparison={data.alert} label="Midterm alert rate, all courses" groupIsEveryone={everyone} />
      </li>
      <li>
        <ComparisonTile comparison={data.recovery} label="Recovered after an alert" groupIsEveryone={everyone} />
      </li>
      <li>
        {everyone ? (
          <StatTile value={data.courses_considered} label="Courses looked at" detail={detail} />
        ) : (
          <StatTile value={`${shown} of ${data.courses_considered}`} label="Courses with the group shown" detail={detail} />
        )}
      </li>
    </ul>
  );
}

/** The group's rate as the headline, with everyone's rate and the difference underneath; only everyone's rate when the group is everyone. */
function ComparisonTile({ comparison, label, groupIsEveryone }: { comparison: Comparison; label: string; groupIsEveryone: boolean }) {
  const { group, everyone, difference_pts: difference } = comparison;
  if (groupIsEveryone) {
    return <StatTile value={everyone.rate === null ? "Hidden" : `${everyone.rate}%`} label={label} detail="Everyone" />;
  }
  const everyoneText = everyone.rate === null ? "Everyone: hidden" : `Everyone: ${everyone.rate}%`;
  return (
    <StatTile
      value={group.rate === null ? "Hidden" : `${group.rate}%`}
      label={label}
      detail={difference === null ? everyoneText : `${everyoneText} · ${formatPoints(difference)}`}
    />
  );
}

/** How many courses were looked at, how many show the group, and the widest difference. */
function Headlines({ data }: { data: Courses }) {
  if (isEveryone(data.race, data.gender)) return <EveryoneHeadlines data={data} />;
  const shown = data.courses_considered - data.courses_with_group_hidden;
  const widest = data.rows
    .filter((row) => row.difference_pts !== null)
    .sort((a, b) => (b.difference_pts ?? 0) - (a.difference_pts ?? 0))[0];
  return (
    <ul className="grid gap-3 sm:grid-cols-3">
      <li>
        <StatTile value={data.courses_considered} label="Courses looked at" detail={`${data.min_enrollments}+ graded enrollments`} />
      </li>
      <li>
        <StatTile value={shown} label="With the group shown" detail="The rest have under 10 of its students" />
      </li>
      <li>
        <StatTile
          value={widest?.difference_pts != null ? formatPoints(widest.difference_pts) : "—"}
          label={widest ? `Widest difference: ${widest.course}` : "No course shows the group"}
          detail="Group DFW minus everyone's"
        />
      </li>
    </ul>
  );
}

/** With everyone as the group there is no difference: how many courses were looked at, and the highest DFW listed. */
function EveryoneHeadlines({ data }: { data: Courses }) {
  const highest = data.rows
    .filter((row) => row.everyone.rate !== null)
    .sort((a, b) => (b.everyone.rate ?? 0) - (a.everyone.rate ?? 0))[0];
  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      <li>
        <StatTile value={data.courses_considered} label="Courses looked at" detail={`${data.min_enrollments}+ graded enrollments`} />
      </li>
      <li>
        <StatTile
          value={highest?.everyone.rate != null ? `${highest.everyone.rate}%` : "—"}
          label={highest ? `Highest DFW: ${highest.course}` : "No course shown"}
          detail="Of the courses listed"
        />
      </li>
    </ul>
  );
}

/** What each bar colour stands for. `name` is the server's group label, or null when the group is everyone and there is only everyone's bar. */
function Legend({ name }: { name: string | null }) {
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
      {name !== null && (
        <li className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-full" style={{ backgroundColor: GROUP_COLOR }} /> {name}
        </li>
      )}
      <li className="flex items-center gap-1.5">
        <span className="size-2.5 rounded-full" style={{ backgroundColor: EVERYONE_COLOR }} /> Everyone in the course
      </li>
      <li>Lower is better</li>
    </ul>
  );
}

/** One course: the group's bar over everyone's, and the difference; only everyone's bar when the group is everyone. */
function CourseLine({ row, everyone }: { row: CourseRow; everyone: boolean }) {
  return (
    <li className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="font-semibold">{row.course}</span>
        {!everyone && (
          <span className="tabular-nums text-muted-foreground">
            {row.difference_pts === null ? "Group hidden" : formatPoints(row.difference_pts)}
          </span>
        )}
      </div>
      {!everyone && <Bar rate={row.group} color={GROUP_COLOR} />}
      <Bar rate={row.everyone} color={EVERYONE_COLOR} />
    </li>
  );
}

/** A 0–100% bar with the rate and enrollments on the right. */
function Bar({ rate, color }: { rate: Rate; color: string }) {
  const text = rate.rate === null || rate.n === null ? "Hidden" : `${rate.rate}% · ${rate.n.toLocaleString()} enrollments`;
  return (
    <div className="flex items-center gap-3">
      <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-muted" role="presentation">
        <div className="h-full rounded-full" style={{ width: `${rate.rate ?? 0}%`, backgroundColor: color }} />
      </div>
      <span className="w-52 shrink-0 text-right text-xs tabular-nums text-muted-foreground">{text}</span>
    </div>
  );
}
