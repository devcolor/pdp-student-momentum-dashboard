import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect } from "storybook/test";
import { sidebarDestinations } from "@/components/testing/navigation-panel-fixtures";
import { mockSavedTables } from "@/components/testing/upload-fixtures";
import type { PublishResult } from "@/services/workbench";
import { progressNote, publishLines } from "@/services/workbench-mappers";
import { UploadSavedCallout } from "./upload-saved-callout";

const meta = {
  component: UploadSavedCallout, title: "Workbench/Upload/Upload saved callout",
  args: { tables: mockSavedTables, joinKey: "Student ID + Cohort", exploreHref: sidebarDestinations.explore },
} satisfies Meta<typeof UploadSavedCallout>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  name: "Default: Two tables saved to database",
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("heading", { level: 2, name: "Saved" })).toBeVisible();
    await expect(canvas.getByRole("status")).toHaveTextContent(
      "2 tables are in the local database: cohort (10,313 rows) and course (100,951 rows), linked on Student ID + Cohort.",
    );
    await expect(canvas.getByRole("link", { name: "Explore the data" })).toHaveAttribute("href", sidebarDestinations.explore);
  },
};

/** Three synthetic tables use a serial comma and keep each table name bold. */
export const ThreeTables: Story = {
  name: "Three table summary",
  args: { tables: [...mockSavedTables, { name: "holds", rowCount: 10313 }], joinKey: undefined },
  play: async ({ canvas }) => {
    const status = canvas.getByRole("status");
    await expect(status).toHaveTextContent(
      "3 tables are in the local database: cohort (10,313 rows), course (100,951 rows), and holds (10,313 rows).",
    );
    await expect(Array.from(status.querySelectorAll("strong"), (name) => name.textContent)).toEqual([
      "cohort", "course", "holds",
    ]);
  },
};

/** Every save also loads the committed enrichment files, so the callout can say so underneath. */
export const WithEnrichmentNote: Story = {
  name: "With enrichment note",
  args: {
    children: <p>The on-campus housing and institution events files were loaded too.</p>,
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText(/on-campus housing/)).toBeVisible();
  },
};

const failedPublish: PublishResult = {
  status: "failed",
  message:
    "Tables loaded, but the published results weren't rebuilt: no students in cohort 2021-22 in the loaded data " +
    "(it has 2022-23). Those views still show the earlier results.",
  manifest_version: null,
  data_loaded_at: null,
};

/** The run's publish line in the Saved step, from publishLines: a failed publish is a line, not an error. */
export const WithPublishLine: Story = {
  name: "With publish line",
  args: {
    children: (
      <ul className="list-disc pl-5">
        {publishLines(failedPublish).map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    ),
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("heading", { level: 2, name: "Saved" })).toBeVisible();
    await expect(canvas.getByText(/published results weren't rebuilt: no students in cohort 2021-22/)).toBeVisible();
    await expect(canvas.queryByRole("alert")).toBeNull();
    // Still running: no line yet, and the progress note says what the run is doing.
    const message = "Rebuilding the published results (about a minute).";
    const running: PublishResult = { status: "running", message, manifest_version: null, data_loaded_at: null };
    await expect(publishLines(running)).toEqual([]);
    await expect(progressNote(["map: done", "load: done"], running)).toBe(message);
    // Without the server's message (an older server), the load's own note shows.
    await expect(progressNote(["map: done", "load: done"], { ...running, message: "" })).toBe("Loading… done: map, load.");
    await expect(progressNote(["map: done", "load: done"])).toBe("Loading… done: map, load.");
  },
};
