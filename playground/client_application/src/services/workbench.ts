import { apiRequest } from "@/lib/api-client";

/** Mirrors server_application/app/sandbox/pipeline/schemas.py and dictionary/schemas.py. */

export type SourceKind = "cohort" | "course";
/** An upload is a cohort or course file, or an institution's supplemental file. */
export type UploadKind = SourceKind | "supplemental";
export type RunState = "running" | "succeeded" | "failed";

/** What a supplemental upload holds once its columns become attributes. */
export type SupplementalSummary = {
  rows_read: number;
  facts: number;
  rows_set_aside: number;
  attributes: string[];
  per_term: boolean;
  source?: string | null;
};

export type Upload = {
  upload_id: string;
  kind: UploadKind;
  filename: string;
  size_bytes: number;
  sha256: string;
  uploaded_at: string;
  unexpected_columns: string[];
  supplemental?: SupplementalSummary | null;
  /** A supplemental upload's values in the database now; null for other kinds, or when another upload shares them. */
  values_loaded?: number | null;
};

/** An upload that was removed, with how many of its values left the database. */
export type RemovedUpload = { upload_id: string; filename: string; values_removed: number };
/** A supplemental file that's part of the data model itself: read-only. */
export type BuiltInFile = { file: string; values: number; attributes: string[] };
export type UploadList = { uploads: Upload[]; built_in?: BuiltInFile[] };

/** How one supplemental upload loaded. */
export type SupplementalResult = { upload_id: string; filename: string; facts_loaded: number; facts_held_back: number };

/** One source file's validation counts in a load summary. */
export type FileValidation = { run_id?: string; rows_read: number; rows_passed: number; rows_failed: number };

/** The parts of the loader's summary the workbench reads; the server sends more. */
export type LoadSummary = {
  run_id?: string;
  status?: string;
  validation?: Record<string, FileValidation>;
  fixes?: Record<string, number>;
  tables?: Record<string, number>;
  held_back_rows?: number;
};

/** Whether a run rebuilt the published results the results pages read. It never changes the run's own status. */
export type PublishResult = {
  status: "running" | "published" | "skipped" | "failed";
  message: string;
  manifest_version: number | null;
  data_loaded_at: string | null;
};

export type RunStatus = {
  run_id: string;
  status: RunState;
  cohort_upload_id: string | null;
  course_upload_id: string | null;
  supplemental?: SupplementalResult[];
  started_at: string | null;
  finished_at: string | null;
  progress: string[];
  error_kind: "invalid_input" | "load_failed" | null;
  error: string | null;
  summary: LoadSummary | null;
  publish?: PublishResult | null;
  note: string;
};

export type RunRequest = { cohort_upload_id?: string; course_upload_id?: string; supplemental_upload_ids?: string[] };

export type TableSummary = { name: string; row_count: number | null };
export type TableList = { tables: TableSummary[]; note: string };
export type TableRows = { name: string; columns: string[]; rows: Record<string, unknown>[]; limit: number; offset: number; note: string };

export type ColumnDefinition = {
  table: string;
  column: string;
  dictionary_name: string | null;
  description_source: string | null;
  description: string | null;
  dictionary_values: { code: string; meaning: string | null }[];
  notes: string | null;
  sources: {
    source_file: string;
    source_column: string;
    dictionary_file: string | null;
    lookup_description: string | null;
  }[];
  stored: { type: string; nullable: boolean; unknown_value: string | null; allowed_values: string[] | null };
};

export type ColumnDefinitionList = { columns: ColumnDefinition[]; note: string };

/** Every normalized column's dictionary definition. */
export function listColumns(): Promise<ColumnDefinitionList> {
  return apiRequest<ColumnDefinitionList>("/sandbox/dictionary/columns", { cache: "no-store" });
}

/** Every model table and its row count; null counts before the first load. */
export function listTables(): Promise<TableList> {
  return apiRequest<TableList>("/sandbox/pipeline/tables", { cache: "no-store" });
}

/** `limit` rows of one model table from `offset`, in primary key order. 404s before the table's first load. */
export function getTableRows(name: string, limit = 50, offset = 0): Promise<TableRows> {
  return apiRequest<TableRows>(`/sandbox/pipeline/tables/${encodeURIComponent(name)}?limit=${limit}&offset=${offset}`, { cache: "no-store" });
}

/** Start loading the given uploads; a file left out is the repo's mock file. */
export function startRun(request: RunRequest, signal?: AbortSignal): Promise<RunStatus> {
  return apiRequest<RunStatus>("/sandbox/pipeline/runs", { method: "POST", json: request, signal });
}

/** One run's status and, once it ends, the loader's summary. */
export function getRun(runId: string, signal?: AbortSignal): Promise<RunStatus> {
  return apiRequest<RunStatus>(`/sandbox/pipeline/runs/${encodeURIComponent(runId)}`, { cache: "no-store", signal });
}

// Larger CSV files need more time to reach the server.
const UPLOAD_TIMEOUT_MS = 120_000;

/** Store one CSV as the cohort or course file. The server refuses one missing a mapped column. */
/** Every stored upload, newest first. */
export function listUploads(): Promise<UploadList> {
  return apiRequest<UploadList>("/sandbox/pipeline/uploads", { cache: "no-store" });
}

/** Delete an upload's files and, for a supplemental upload, its values in the database. */
export function removeUpload(uploadId: string): Promise<RemovedUpload> {
  return apiRequest<RemovedUpload>(`/sandbox/pipeline/uploads/${encodeURIComponent(uploadId)}`, { method: "DELETE" });
}

export function createUpload(kind: UploadKind, file: File): Promise<Upload> {
  const formData = new FormData();
  formData.append("kind", kind);
  formData.append("file", file);
  return apiRequest<Upload>("/sandbox/pipeline/uploads", { method: "POST", formData, timeoutMs: UPLOAD_TIMEOUT_MS });
}

