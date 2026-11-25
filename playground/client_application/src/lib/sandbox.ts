import { apiRequest } from "@/lib/api-client";
import type { Schemas } from "@/lib/api/types";

/** Types and loaders shared by every sandbox page and chart component. Types come from the server's OpenAPI schema. */

export type ChartMeta = Schemas["ChartMeta"];

/** Every chart answers with its meta plus one row per point or bar. */
export type ChartResponse<Row> = { meta: ChartMeta; rows: Row[] };

/** Which way a KPI moved, and whether that move is better, the same, or worse. */
export type KpiTrend = Schemas["KpiTrend"];

/** A KPI tile. Only the server's TrendKpi sends trend, so it is optional here. */
export type Kpi = Schemas["Kpi"] & Partial<Pick<Schemas["TrendKpi"], "trend">>;

export type KpiResponse = { meta: ChartMeta; items: Kpi[] };

/** Loads one sandbox endpoint. `path` is what it fetches, relative to the API base URL. */
export type SandboxLoader<T> = (() => Promise<T>) & { path: string };

/** A loader for one sandbox endpoint, e.g. sandboxLoader("/chart-examples") fetches /api/v1/sandbox/chart-examples. */
export function sandboxLoader<T>(endpoint: string): SandboxLoader<T> {
  const path = `/sandbox${endpoint}`;
  return Object.assign(() => apiRequest<T>(path, { cache: "no-store" }), { path });
}

/** Loads one chart by name from a page's endpoint, so each card keeps its own loading and errors. */
export function chartLoader<Chart>(endpoint: string, chartName: string): SandboxLoader<Chart> {
  const load = sandboxLoader<Record<string, Chart>>(`${endpoint}?charts=${chartName}`);
  return Object.assign(() => load().then((charts) => charts[chartName]), { path: load.path });
}
