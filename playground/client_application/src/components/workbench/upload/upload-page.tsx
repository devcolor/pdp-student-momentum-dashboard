"use client";

import type { ComponentProps } from "react";
import { CircleX } from "lucide-react";
import { PageIntro } from "@/components/page-intro";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { CheckResultsList } from "@/components/workbench/upload/check-results-list";
import { FileDropzone } from "@/components/workbench/upload/file-dropzone";
import { UploadSavedCallout } from "@/components/workbench/upload/upload-saved-callout";
import { UploadSteps } from "@/components/workbench/upload/upload-steps";
import { UploadedFileList } from "@/components/workbench/upload/uploaded-file-list";
import { YourUploads } from "@/components/workbench/upload/your-uploads";

export type UploadStage = "choose" | "checking" | "checked" | "saved";
export type UploadPageProps = {
  stage: UploadStage;
  error?: string;
  steps: ComponentProps<typeof UploadSteps>;
  dropzone: Omit<ComponentProps<typeof FileDropzone>, "onRejectedFiles">;
  /** Lets the route explain why a picked or dropped file was refused. */
  onRejectedFiles?: ComponentProps<typeof FileDropzone>["onRejectedFiles"];
  files: ComponentProps<typeof UploadedFileList>;
  checks: ComponentProps<typeof CheckResultsList>;
  saved: ComponentProps<typeof UploadSavedCallout>;
  /** The stored uploads, listed under the dropzone, each one removable. */
  yourUploads?: ComponentProps<typeof YourUploads>;
};

/** Presents an upload stage while the caller owns checking, saving and navigation. */
export function UploadPage({ stage, error, steps, dropzone, onRejectedFiles, files, checks, saved, yourUploads }: UploadPageProps) {
  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <PageIntro size="sm" title="Upload data">
        <p>
          Add your cohort and course files, plus any supplemental data your institution keeps where the PDP files fall
          short. They&apos;re checked, then saved to the database.
        </p>
      </PageIntro>
      <UploadSteps {...steps} />
      {error && (
        <Alert variant="destructive">
          <CircleX aria-hidden />
          <AlertTitle>That didn&apos;t go through</AlertTitle>
          <AlertDescription>
            <p>{error}</p>
          </AlertDescription>
        </Alert>
      )}
      {stage === "choose" && <FileDropzone {...dropzone} onRejectedFiles={onRejectedFiles} />}
      {stage === "choose" && yourUploads && <YourUploads {...yourUploads} />}
      {stage !== "choose" && <UploadedFileList {...files} />}
      {stage === "checked" && <CheckResultsList {...checks} />}
      {stage === "saved" && <UploadSavedCallout {...saved} />}
    </div>
  );
}
