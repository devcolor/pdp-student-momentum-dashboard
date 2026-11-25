"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { ChartCard } from "@/components/sandbox/chart-card";
import { FilterSelect } from "@/components/sandbox/filter-select";
import { routes } from "@/lib/routes";

import { type CohortLens, type CourseLoadFilters, type SupplementalFile, supplementalLoader } from "./data";

type SupplementalCardProps = { cohort: CohortLens; filters: CourseLoadFilters };

/** The institution's uploaded supplemental files, one at a time, picked from a dropdown. */
export function SupplementalCard({ cohort, filters }: SupplementalCardProps) {
  const load = useMemo(() => supplementalLoader(cohort, filters), [cohort, filters]);
  return (
    <ChartCard load={load} compact>
      {(data) => (data.files.length === 0 ? <EmptyState /> : <FilePicker files={data.files} />)}
    </ChartCard>
  );
}

/** A dropdown of the uploaded files and the chosen file's table. Starts on the first file. */
function FilePicker({ files }: { files: SupplementalFile[] }) {
  const [chosen, setChosen] = useState<string>();
  const keys = files.map(fileKey);
  // A file can drop out when the cohort or filters change; then show the first one.
  const key = chosen && keys.includes(chosen) ? chosen : keys[0];
  const file = files[keys.indexOf(key)];
  const labels = Object.fromEntries(files.map((one) => [fileKey(one), fileLabel(one, files)]));

  return (
    <div className="flex flex-col gap-4">
      <div className="max-w-md">
        <FilterSelect id="supplemental-file" label="File" value={key} values={keys} labels={labels} onChange={setChosen} />
      </div>
      <FileTable file={file} />
    </div>
  );
}

/** What tells one uploaded file apart: its upload id, or its name and date for an older upload. */
function fileKey(file: SupplementalFile): string {
  return file.upload_id ?? `${file.file}|${file.uploaded_on ?? ""}`;
}

/** A file's name and upload date, plus its id when another file reads the same. */
function fileLabel(file: SupplementalFile, files: SupplementalFile[]): string {
  const label = file.uploaded_on ? `${file.file} · uploaded ${file.uploaded_on}` : file.file;
  const twins = files.filter((other) => other.file === file.file && other.uploaded_on === file.uploaded_on);
  return twins.length > 1 && file.upload_id ? `${label} (${file.upload_id.slice(0, 6)})` : label;
}

const cell = "border px-3 py-1.5 whitespace-nowrap";

/** One file as a spreadsheet: Student ID, the term for a per-term file, then each uploaded column. */
function FileTable({ file }: { file: SupplementalFile }) {
  const students = `${file.students.toLocaleString()} ${file.students === 1 ? "student" : "students"}`;
  return (
    <section className="flex min-w-0 flex-col gap-2">
      <p className="text-xs text-muted-foreground">{students}</p>
      <div className="max-h-[28rem] overflow-auto rounded-md border">
            <table className="w-full border-collapse text-xs tabular-nums">
              <thead className="sticky top-0 z-10 bg-muted text-left">
                <tr>
                  <th scope="col" className={`${cell} font-semibold`}>Student ID</th>
                  {file.per_term && (
                    <>
                      <th scope="col" className={`${cell} font-semibold`}>Academic year</th>
                      <th scope="col" className={`${cell} font-semibold`}>Term</th>
                    </>
                  )}
                  {file.columns.map((column) => (
                    <th key={column} scope="col" className={`${cell} font-semibold`}>
                      {readableName(column)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {file.rows.map((row) => (
                  <tr key={`${row.student_id}-${row.academic_year}-${row.academic_term}`} className="even:bg-muted/40">
                    <td className={`${cell} font-mono`}>{row.student_id}</td>
                    {file.per_term && (
                      <>
                        <td className={cell}>{row.academic_year}</td>
                        <td className={cell}>{row.academic_term}</td>
                      </>
                    )}
                    {file.columns.map((column) => (
                      <td key={column} className={cell}>
                        {row.values[column] ?? ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
      {file.total_rows > file.rows.length && (
        <p className="text-xs text-muted-foreground">
          Showing the first {file.rows.length.toLocaleString()} of {file.total_rows.toLocaleString()} rows.
        </p>
      )}
    </section>
  );
}

/** What to do when nothing is uploaded, as on the deployed site, which can't save. */
function EmptyState() {
  return (
    <p className="text-sm text-muted-foreground">
      No supplemental data is loaded. Upload a supplemental file on the{" "}
      <Link className="underline underline-offset-2" href={routes.workbenchUpload}>
        Workbench Upload page
      </Link>{" "}
      on a local copy; the deployed site can&apos;t save uploads.
    </p>
  );
}

/** An attribute name as a column heading: "advising_visits" reads "Advising visits". */
function readableName(attribute: string): string {
  const words = attribute.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
