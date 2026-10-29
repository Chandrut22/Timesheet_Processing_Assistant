// The Upload page: a full-page screen (staticData.fullWidth). On large screens it fills
// the viewport and never scrolls as a whole; its panels scroll inside. This file only
// composes the pieces in this feature and owns the upload itself.
// import { UploadGuide } from "./UploadGuide";
import { useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type JSX } from "react";
import { toast } from "sonner";
import { errorMessage } from "@/services/apiErrors";
import { DropOverlay } from "./DropOverlay";
import { RecentUploads } from "./RecentUploads";
import { SelectedFiles } from "./SelectedFiles";
import { UploadDropzone } from "./UploadDropzone";
import { MobileUploadBar, UploadSettings } from "./UploadSettings";
import { totalBytes, validateFiles } from "../utils/uploadLimits";
import { useWindowFileDrop } from "../hooks/useWindowFileDrop";
import { uploadService } from "../services/uploadService";
import { submissionKeys } from "@/features/submissions";

export function UploadPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [problems, setProblems] = useState<string[]>([]);
  const [companyId, setCompanyId] = useState("");
  const [progress, setProgress] = useState<number | null>(null);

  const upload = useMutation({
    mutationFn: () => uploadService.upload(files, companyId || undefined, setProgress),
    meta: { silentError: true },
    onSuccess: (submission) => {
      toast.success("Uploaded. Processing has started.");
      void queryClient.invalidateQueries({ queryKey: submissionKeys.all });
      void navigate({ to: "/submissions/$submissionId", params: { submissionId: submission.id } });
    },
    onSettled: () => setProgress(null),
  });
  const pending = upload.isPending;

  const addFiles = (incoming: File[]): void => {
    const result = validateFiles(files, incoming);
    setFiles(result.files);
    setProblems(result.problems);
  };
  const { dragging } = useWindowFileDrop(addFiles, { enabled: !pending });

  const bytes = totalBytes(files);
  const uploadState = {
    fileCount: files.length,
    totalBytes: bytes,
    pending,
    progress,
    onUpload: () => upload.mutate(),
  };

  return (
    <div className="relative flex flex-col gap-4 lg:min-h-0 lg:flex-1">
      <DropOverlay visible={dragging} />
      <div className="shrink-0">
        <h1 className="text-xl font-semibold tracking-tight">Upload timesheets</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          For timesheets that didn't arrive by email. They go through the same reading and checks.
        </p>
      </div>

      <div className="flex flex-col gap-4 lg:min-h-0 lg:flex-1 lg:flex-row">
        {/* Left: drop area and the chosen files */}
        <section
          aria-label="Files"
          className="relative flex min-h-[22rem] flex-col gap-3 overflow-hidden rounded-lg border bg-card p-4 lg:min-h-0 lg:flex-1"
        >
          {pending ? (
            <div className="absolute inset-x-0 top-0 h-1 bg-muted" aria-hidden>
              <div
                className="h-full bg-primary transition-[width] motion-reduce:transition-none"
                style={{ width: `${progress ?? 0}%` }}
              />
            </div>
          ) : null}
          <UploadDropzone
            fileCount={files.length}
            totalBytes={bytes}
            compact={files.length > 0}
            disabled={pending}
            problems={problems}
            onFiles={addFiles}
          />
          {files.length > 0 ? (
            <SelectedFiles
              files={files}
              disabled={pending}
              onRemove={(i) => setFiles(files.filter((_, j) => j !== i))}
              onClear={() => {
                setFiles([]);
                setProblems([]);
              }}
            />
          ) : null}
        </section>

        {/* Right: settings, recent uploads, guide (scrolls inside on large screens) */}
        <aside
          aria-label="Upload settings and help"
          className="flex flex-col gap-4 lg:min-h-0 lg:w-[380px] lg:shrink-0 lg:overflow-y-auto"
        >
          <UploadSettings
            {...uploadState}
            companyId={companyId}
            onCompany={setCompanyId}
            error={upload.error ? errorMessage(upload.error) : null}
            className="lg:sticky lg:top-0 lg:z-10"
          />
          <RecentUploads className="lg:min-h-64 lg:flex-1" />
          {/* <UploadGuide className="shrink-0" /> */}
        </aside>
      </div>

      <MobileUploadBar {...uploadState} />
    </div>
  );
}
