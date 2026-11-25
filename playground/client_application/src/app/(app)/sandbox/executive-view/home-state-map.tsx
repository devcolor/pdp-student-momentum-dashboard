"use client";

import { geoPath } from "d3-geo";
import type { Feature, Geometry } from "geojson";
import { useMemo } from "react";
import { feature } from "topojson-client";
import type { GeometryCollection, Topology } from "topojson-specification";
import statesAtlas from "us-atlas/states-albers-10m.json";

import { ChartCard } from "@/components/sandbox/chart-card";

import { type CohortLens, type CourseLoadFilters, type HomeStateRow, homeStatesLoader } from "./data";

// Traffic-light colors by rank. Light enough that the dark labels read in both themes.
const BAND_SIZE = 5;
const BAND_FILLS = {
  top: "#4ade80",
  next: "#facc15",
  rest: "#f87171",
  // A light neutral, a step off the card in both themes, so states without students still read as land.
  none: "color-mix(in oklab, var(--foreground) 12%, var(--background))",
};
// State borders: visible on the card in both themes, and between neighbors of the same color.
const BORDER = "color-mix(in oklab, var(--foreground) 35%, var(--background))";
// us-atlas's Albers file is already projected to this size, with Alaska and Hawaii moved under the lower 48.
const MAP_WIDTH = 975;
const MAP_HEIGHT = 610;

// us-atlas names states by FIPS code; the API by postal code.
const POSTAL_BY_FIPS: Record<string, string> = {
  "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC",
  "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
  "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT",
  "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
  "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
  "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI", "56": "WY", "72": "PR",
};

type StateShape = { postal: string; name: string; path: string; centroid: [number, number] };

// The shapes never change, so they're worked out once when the module loads.
const STATE_SHAPES: StateShape[] = buildShapes();

/** Every state's outline as an SVG path, with its postal code, name and center point. */
function buildShapes(): StateShape[] {
  const topology = statesAtlas as unknown as Topology<{ states: GeometryCollection<{ name: string }> }>;
  const collection = feature(topology, topology.objects.states);
  const path = geoPath();
  return collection.features.map((shape: Feature<Geometry, { name: string }>) => ({
    postal: POSTAL_BY_FIPS[String(shape.id)] ?? String(shape.id),
    name: shape.properties.name,
    path: path(shape) ?? "",
    centroid: path.centroid(shape),
  }));
}

type HomeStateMapCardProps = { cohort: CohortLens; filters: CourseLoadFilters };

/** Headcount by home state as a US map, following the page's cohort and filters. */
export function HomeStateMapCard({ cohort, filters }: HomeStateMapCardProps) {
  const load = useMemo(() => homeStatesLoader(cohort, filters), [cohort, filters]);
  return (
    <ChartCard
      id="exec-home-state"
      load={load}
      compact
      className="scroll-mt-16"
    >
      {(data) => (
        // Map and table side by side on wide screens, so the map fills the card; stacked when narrow.
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem] lg:items-start">
          <StateMap rows={data.rows} />
          <StateTable rows={data.rows} />
        </div>
      )}
    </ChartCard>
  );
}

/** The US map, each state colored by its rank: top 5 green, next 5 yellow, the rest red. */
function StateMap({ rows }: { rows: HomeStateRow[] }) {
  const byState = new Map(rows.map((row) => [row.state, row]));
  const bands = rankBands(rows);

  return (
    <div className="flex flex-col gap-3">
      <svg
        viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
        className="h-auto w-full"
        role="img"
        aria-label="Map of students by home state: top 5 states green, next 5 yellow, the rest red. The table beside it lists the numbers."
      >
        {STATE_SHAPES.map((shape) => {
          const data = byState.get(shape.postal);
          const band = data === undefined ? "none" : (bands.get(shape.postal) ?? "rest");
          return (
            <path key={shape.postal} d={shape.path} fill={BAND_FILLS[band]} stroke={BORDER} strokeWidth={1}>
              <title>{stateLabel(shape.name, data)}</title>
            </path>
          );
        })}
        {STATE_SHAPES.map((shape) => {
          const n = byState.get(shape.postal)?.n;
          if (n === null || n === undefined) return null;
          const [x, y] = shape.centroid;
          return (
            <text
              key={`${shape.postal}-label`}
              x={x}
              y={y}
              textAnchor="middle"
              className="pointer-events-none text-[13px] font-semibold tabular-nums"
              fill="#111827"
            >
              <tspan x={x} dy="-0.2em">
                {shape.postal}
              </tspan>
              <tspan x={x} dy="1.1em" className="font-normal">
                {n.toLocaleString()}
              </tspan>
            </text>
          );
        })}
      </svg>
      <BandKey />
    </div>
  );
}

type Band = keyof typeof BAND_FILLS;

/**
 * Each shown state's band by headcount: the top 5, then the next 5. A state tied with the last one in a
 * band joins it, so equal counts always share a color. Hidden states rank last.
 */
function rankBands(rows: HomeStateRow[]): Map<string, Band> {
  const counts = rows
    .filter((row) => row.n !== null && row.state !== "UNKNOWN")
    .map((row) => row.n ?? 0)
    .sort((a, b) => b - a);
  const topCutoff = counts[BAND_SIZE - 1] ?? 0;
  const topSize = counts.filter((n) => n >= topCutoff).length;
  const nextCutoff = counts[topSize + BAND_SIZE - 1] ?? 0;

  const bands = new Map<string, Band>();
  for (const row of rows) {
    if (row.n === null || row.state === "UNKNOWN") continue;
    if (row.n >= topCutoff) bands.set(row.state, "top");
    else if (row.n >= nextCutoff) bands.set(row.state, "next");
  }
  return bands;
}

/** What a state's hover text says. Exported for its story: the map itself needs the atlas.

 * The share, not the count: the map already prints the count on the state itself, and the table
 * beside it carries both.
 */
export function stateLabel(name: string, data: HomeStateRow | undefined): string {
  if (data === undefined) return `${name}: no students`;
  if (data.share === null) return `${name}: hidden to protect small counts`;
  return `${name}: ${data.share}% of students`;
}

/** A short key for the colors. */
function BandKey() {
  const items: { band: Band; label: string }[] = [
    { band: "top", label: `Top ${BAND_SIZE} states` },
    { band: "next", label: `Next ${BAND_SIZE}` },
    { band: "rest", label: "All other states with students" },
    { band: "none", label: "No students" },
  ];
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      {items.map(({ band, label }) => (
        <span key={band} className="flex items-center gap-1.5">
          <span className="inline-block size-3 rounded-sm border" style={{ backgroundColor: BAND_FILLS[band] }} />
          {label}
        </span>
      ))}
    </div>
  );
}

/** The numbers behind the map, so no reading depends on color or hover. */
function StateTable({ rows }: { rows: HomeStateRow[] }) {
  return (
    <div className="max-h-56 overflow-y-auto lg:max-h-[30rem]">
      <table className="w-full text-xs tabular-nums">
        <thead>
          <tr className="text-muted-foreground">
            <th scope="col" className="py-1.5 text-left font-normal">Home state</th>
            <th scope="col" className="py-1.5 text-right font-normal">Students</th>
            <th scope="col" className="py-1.5 text-right font-normal">Share</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.state} className="border-t">
              <th scope="row" className="py-1.5 text-left font-normal">{row.state === "UNKNOWN" ? "Unknown" : row.state}</th>
              <td className="py-1.5 text-right font-semibold">{row.n === null ? "Hidden" : row.n.toLocaleString()}</td>
              <td className="py-1.5 text-right">{row.share === null ? "—" : `${row.share}%`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
