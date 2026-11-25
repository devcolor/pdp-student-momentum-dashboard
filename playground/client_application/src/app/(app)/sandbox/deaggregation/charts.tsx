"use client";

import { useMemo, useState } from "react";

import { ChatPageContext } from "@/components/chat/chat-page-context";
import { ChartCard } from "@/components/sandbox/chart-card";
import { FilterSelect } from "@/components/sandbox/filter-select";
import { PinnedFilters } from "@/components/sandbox/pinned-filters";
import { StatTile } from "@/components/stat-tile";
import { seriesColor } from "@/lib/charts";

import { formatPoints, formatRate, gapSummary, groupName, otherGroupName, realGapsBehind } from "./chart-config";
import {
  type Gender,
  type GroupPicks,
  type OutcomeRow,
  type Race,
  type Rate,
  genderLabels,
  genders,
  outcomesLoader,
  raceLabels,
  races,
} from "./data";

/** Bar colours from the chosen chart palette; everyone stays neutral so the groups stand out. */
const GROUP_COLOR = seriesColor(0);
const OTHER_GENDER_COLOR = seriesColor(1);
const EVERYONE_COLOR = "color-mix(in oklab, var(--foreground) 40%, transparent)";

/** Pick a group, then read every measure for it beside the other gender and everyone. `initial` comes from the page's link. */
export function Charts({ initial }: { initial: GroupPicks }) {
  const [race, setRace] = useState<Race>(initial.race);
  const [gender, setGender] = useState<Gender>(initial.gender);
  const load = useMemo(() => outcomesLoader(race, gender), [race, gender]);

  return (
    <div className="flex max-w-4xl flex-col gap-4">
      <PinnedFilters>
        <div className="grid gap-4 sm:grid-cols-2">
          <FilterSelect id="gender" label="Gender" value={gender} values={genders} labels={genderLabels} onChange={setGender} />
          <FilterSelect id="race" label="Race" value={race} values={races} labels={raceLabels} onChange={setRace} />
        </div>
      </PinnedFilters>

      <ChartCard id="deaggregation-outcomes" load={load}>
        {(data) => (
          <div className="flex flex-col gap-8">
            <ChatPageContext page={{ title: data.meta.title, filters: data.meta.filters, specs: data.meta.specs }} />
            <Headlines rows={data.rows} />
            <Legend race={data.race} gender={data.gender} />
            <ul className="flex flex-col gap-6">
              {data.rows.map((row) => (
                <MeasureRow key={row.measure} row={row} />
              ))}
            </ul>
          </div>
        )}
      </ChartCard>
    </div>
  );
}

/** The widest tested gap, how many hold up, and how often the group ranks most behind. */
function Headlines({ rows }: { rows: OutcomeRow[] }) {
  const real = realGapsBehind(rows);
  const widest = [...real].sort((a, b) => (a.gap_pts ?? 0) - (b.gap_pts ?? 0))[0];
  const rankedFirst = rows.filter((row) => row.rank === 1);
  return (
    <ul className="grid gap-3 sm:grid-cols-3">
      <li>
        <StatTile
          value={widest?.gap_pts != null ? formatPoints(widest.gap_pts) : "—"}
          label={widest ? `Widest gap: ${widest.label}` : "No gap holds up"}
          detail="Against everyone else"
        />
      </li>
      <li>
        <StatTile value={real.length} label="Gaps behind that aren't noise" detail="Of the yes-or-no measures" />
      </li>
      <li>
        <StatTile value={rankedFirst.length} label="Measures where this group ranks most behind" detail="Among race × gender groups" />
      </li>
    </ul>
  );
}

/** What each bar colour stands for. */
function Legend({ race, gender }: { race: Race; gender: Gender }) {
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
      <li className="flex items-center gap-1.5">
        <span className="size-2.5 rounded-full" style={{ backgroundColor: GROUP_COLOR }} /> {groupName(race, gender)}
      </li>
      <li className="flex items-center gap-1.5">
        <span className="size-2.5 rounded-full" style={{ backgroundColor: OTHER_GENDER_COLOR }} /> {otherGroupName(race, gender)}
      </li>
      <li className="flex items-center gap-1.5">
        <span className="size-2.5 rounded-full" style={{ backgroundColor: EVERYONE_COLOR }} /> Everyone
      </li>
    </ul>
  );
}

/** One measure: three bars, then the gap line. */
function MeasureRow({ row }: { row: OutcomeRow }) {
  const behindAndReal = row.gap_pts !== null && row.gap_pts < 0 && row.likely_noise === false;
  return (
    <li className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <h4 className="text-sm font-semibold">{row.label}</h4>
        {row.lower_is_better && <span className="text-xs text-muted-foreground">Lower is better</span>}
      </div>
      <Bar rate={row.group} counts={row.counts} color={GROUP_COLOR} />
      <Bar rate={row.other_gender} counts={row.counts} color={OTHER_GENDER_COLOR} />
      <Bar rate={row.everyone} counts={row.counts} color={EVERYONE_COLOR} />
      <p className={behindAndReal ? "text-sm font-medium" : "text-sm text-muted-foreground"}>
        {gapSummary(row)}
        {row.likely_noise === true && <span className="ml-2 rounded-full border px-2 py-0.5 text-xs">likely noise</span>}
      </p>
    </li>
  );
}

/** A 0–100% bar with its rate and n on the right. */
function Bar({ rate, counts, color }: { rate: Rate; counts: OutcomeRow["counts"]; color: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-muted" role="presentation">
        <div className="h-full rounded-full" style={{ width: `${rate.rate ?? 0}%`, backgroundColor: color }} />
      </div>
      <span className="w-52 shrink-0 text-right text-xs tabular-nums text-muted-foreground">{formatRate(rate, counts)}</span>
    </div>
  );
}
