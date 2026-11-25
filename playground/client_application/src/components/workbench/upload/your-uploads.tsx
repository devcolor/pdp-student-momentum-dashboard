"use client";

import { FileText, Lock, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { BuiltInFile, Upload } from "@/services/workbench";

type YourUploadsProps = {
  /** Null while the list loads. */
  uploads: Upload[] | null;
  /** Deletes one upload; rejects with a message to show if it can't. */
  onRemove: (upload: Upload) => Promise<void>;
  /** Removing is refused while a load runs. */
  disabled?: boolean;
  /** The data model's own supplemental files, listed first, read-only. */
  builtIn?: BuiltInFile[];
};

const KIND_NAMES = { cohort: "Cohort file", course: "Course file", supplemental: "Supplemental" } as const;

/** The files stored so far, newest first. Hover one to remove it; a second click confirms. */
export function YourUploads({ uploads, onRemove, disabled = false, builtIn = [] }: YourUploadsProps) {
  const total = (uploads?.length ?? 0) + builtIn.length;
  return (
    <section aria-labelledby="your-uploads" className="flex flex-col gap-2">
      <h2 id="your-uploads" className="text-sm font-semibold">
        Your uploads {total > 0 && <span className="font-normal text-muted-foreground">({total})</span>}
      </h2>
      {uploads === null ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : total === 0 ? (
        <p className="text-sm text-muted-foreground">No files uploaded yet.</p>
      ) : (
        <ul className="divide-y rounded-md border">
          {builtIn.map((file) => (
            <BuiltInRow key={file.file} file={file} />
          ))}
          {uploads.map((upload) => (
            <UploadRow key={upload.upload_id} upload={upload} onRemove={onRemove} disabled={disabled} />
          ))}
        </ul>
      )}
    </section>
  );
}

/** A file that's part of the data model: shown so people know it's there, but it can't be removed here. */
function BuiltInRow({ file }: { file: BuiltInFile }) {
  return (
    <li className="flex items-center gap-3 px-3 py-2 text-sm">
      <Lock className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{file.file}</p>
        <p className="text-xs text-muted-foreground">
          Built-in sample · {file.values.toLocaleString()} values in the database · {file.attributes.length} columns ·
          part of the data model, so it can&apos;t be removed here
        </p>
      </div>
    </li>
  );
}

type UploadRowProps = { upload: Upload; onRemove: (upload: Upload) => Promise<void>; disabled: boolean };

/** One stored file: its name and details, with Remove showing on hover or focus. */
function UploadRow({ upload, onRemove, disabled }: UploadRowProps) {
  const [confirming, setConfirming] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState<string>();

  /** Remove the upload; on failure, say why and stay. */
  async function remove() {
    setRemoving(true);
    setError(undefined);
    try {
      await onRemove(upload);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
      setRemoving(false);
      setConfirming(false);
    }
  }

  return (
    <li className="group flex flex-col gap-1 px-3 py-2 text-sm">
      <div className="flex items-center gap-3">
        <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium">{upload.filename}</p>
          <p className="text-xs text-muted-foreground">{details(upload)}</p>
        </div>
        {confirming ? (
          <div className="flex shrink-0 items-center gap-1">
            <Button variant="destructive" size="sm" onClick={remove} disabled={removing || disabled}>
              {removing ? "Removing…" : "Remove"}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setConfirming(false)} disabled={removing}>
              Cancel
            </Button>
          </div>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            className="shrink-0 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
            aria-label={`Remove ${upload.filename}`}
            onClick={() => setConfirming(true)}
            disabled={disabled}
          >
            <Trash2 className="size-4" aria-hidden />
            Remove
          </Button>
        )}
      </div>
      {confirming && !removing && <p className="pl-7 text-xs text-muted-foreground">{confirmText(upload)}</p>}
      {error && <p className="pl-7 text-xs text-destructive">{error}</p>}
    </li>
  );
}

/** Kind, date, size and, for supplemental data, its values in the database. */
function details(upload: Upload): string {
  const parts = [
    KIND_NAMES[upload.kind],
    new Date(upload.uploaded_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }),
    formatSize(upload.size_bytes),
  ];
  if (upload.kind === "supplemental") {
    if (upload.values_loaded === null || upload.values_loaded === undefined) parts.push("values shared with another upload of this file");
    else if (upload.values_loaded === 0) parts.push("not in the database");
    else parts.push(`${upload.values_loaded.toLocaleString()} values in the database`);
  }
  return parts.join(" · ");
}

/** What removing it does, said before it happens. */
function confirmText(upload: Upload): string {
  if (upload.kind === "supplemental" && upload.values_loaded) {
    return `Removes the file and its ${upload.values_loaded.toLocaleString()} values from the database. This can't be undone.`;
  }
  if (upload.kind === "supplemental") return "Removes the file. Nothing of it is in the database to remove.";
  return "Removes the stored file. Data already loaded from it stays until the next load.";
}

/** A file size in KB or MB. */
function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
