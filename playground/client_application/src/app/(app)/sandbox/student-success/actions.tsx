"use client";

import { Download } from "lucide-react";
import { useMemo } from "react";

import { BarList } from "@/components/sandbox/bar-list";
import { ChartCard } from "@/components/sandbox/chart-card";
import { TrendPill } from "@/components/sandbox/kpi-grid";
import { StatTile } from "@/components/stat-tile";
import { buttonVariants } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { type BarListItem, formatCount } from "@/lib/charts";
import { cn } from "@/lib/utils";

import type { CohortLens } from "../executive-view/data";
import {
  type ActionBoard,
  type ActionGroupRow,
  actionsLoader,
  actionStudentsUrl,
  type ActionTile,
  type EquityDimension,
  equityDimensionLabels,
  type School,
} from "./data";

type ActionBoardCardProps = { cohort: CohortLens; dimension: EquityDimension; school?: School };

/** The Student Completion Action Board: the action tiles, who is in them, and gateway barriers. */
export function ActionBoardCard({ cohort, dimension, school = "ccac" }: ActionBoardCardProps) {
  const load = useMemo(() => actionsLoader(cohort, dimension, school), [cohort, dimension, school]);

  return (
    <ChartCard id="success-actions" load={load}>
      {(data) => {
        if (data.tiles.length === 0) {
          return <p className="text-sm text-muted-foreground">No fall and spring terms are loaded to compare.</p>;
        }
        // MVSU grants no associate degrees; drop the tile here too, in case an older API still sends it.
        const tiles = school === "mvsu" ? data.tiles.filter((tile) => tile.id !== "near_15") : data.tiles;
        return (
          <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-2">
              <div className="flex justify-end">
                <a
                  href={actionStudentsUrl(cohort, school)}
                  download
                  className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
                >
                  <Download className="size-4" aria-hidden />
                  Export student IDs
                </a>
              </div>
              <ul className={cn("grid grid-cols-1 gap-3 sm:grid-cols-2", tiles.length === 3 ? "lg:grid-cols-3" : "lg:grid-cols-4")}>
                {tiles.map((tile) => (
                  <ActionTileItem key={tile.id} tile={tile} exportUrl={actionStudentsUrl(cohort, school, tile.id)} />
                ))}
              </ul>
            </div>
            {school === "mvsu" ? (
              <GatewayCourses data={data} />
            ) : (
              <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
                <WhereToStart groups={data.groups} dimension={dimension} />
                <GatewayCourses data={data} />
              </div>
            )}
          </div>
        );
      }}
    </ChartCard>
  );
}

/** One action tile: the count, what it means, the next step, and a link to export its students' IDs. */
function ActionTileItem({ tile, exportUrl }: { tile: ActionTile; exportUrl: string }) {
  const value = tile.value === null ? "<10" : formatCount(tile.value);
  const detail = (
    <span className="flex flex-col gap-2">
      <span>{tile.detail}</span>
      <span className="text-foreground">
        <span className="font-medium">Next step: </span>
        {tile.action}
      </span>
    </span>
  );
  const share = tile.share === null ? null : <span className="text-xs text-muted-foreground tabular-nums">{tile.share}% of the cohort</span>;
  const trend = (
    <span className="flex flex-wrap items-center gap-2">
      {tile.trend && <TrendPill trend={tile.trend} />}
      {share}
    </span>
  );

  return (
    <li>
      <StatTile
        value={value}
        label={tile.label}
        labelOnTop
        trend={trend}
        detail={detail}
        className="h-full"
        footer={
          <a
            href={exportUrl}
            download
            className="inline-flex w-fit items-center gap-1 text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          >
            <Download className="size-3.5" aria-hidden />
            Export IDs
          </a>
        }
      />
    </li>
  );
}

const ACTION_COLUMNS: { key: keyof Omit<ActionGroupRow, "group" | "n">; label: string }[] = [
  { key: "priority", label: "Priority" },
  { key: "stopped_out", label: "Stopped" },
  { key: "near_15", label: "Near done" },
  { key: "gateway", label: "Gateway" },
];

/** A count cell; hidden counts read "Hidden", since a count can be hidden to protect another group's. */
function countText(value: number | null): string {
  return value === null ? "Hidden" : formatCount(value);
}

/** Students in each action, by the selected equity group, priority first. */
function WhereToStart({ groups, dimension }: { groups: ActionGroupRow[]; dimension: EquityDimension }) {
  return (
    <section className="flex min-w-0 flex-col gap-3">
      <h4 className="text-sm font-semibold">
        Where to start <span className="font-normal text-muted-foreground">· students by {equityDimensionLabels[dimension].toLowerCase()}</span>
      </h4>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Group</TableHead>
            {ACTION_COLUMNS.map((column) => (
              <TableHead key={column.key} className="text-right">
                {column.label}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {groups.map((group) => (
            <TableRow key={group.group}>
              <TableCell className="font-medium">{group.group}</TableCell>
              {ACTION_COLUMNS.map((column) => (
                <TableCell key={column.key} className="text-right tabular-nums">
                  {countText(group[column.key])}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  );
}

/** Gateway courses with the highest DFW rates. */
function GatewayCourses({ data }: { data: ActionBoard }) {
  const items: BarListItem[] = data.gateway_courses.map((course) => ({
    label: course.course,
    value: course.dfw_rate,
    display: `${course.dfw_rate}% DFW`,
    note: `${course.subject} · ${formatCount(course.n)} grades`,
  }));

  return (
    <section className="flex min-w-0 flex-col gap-3">
      <h4 className="text-sm font-semibold">
        Gateway barriers <span className="font-normal text-muted-foreground">· highest D, F or withdraw rates</span>
      </h4>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No gateway course has enough grades to rank.</p>
      ) : (
        <BarList items={items} color="var(--destructive)" />
      )}
    </section>
  );
}
