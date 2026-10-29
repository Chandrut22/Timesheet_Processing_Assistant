// Company choice, summary and the Upload button (right column), plus the sticky bottom
// bar that carries the same button on small screens.
import { CloudUpload } from "lucide-react";
import { FormError } from "@/components/forms/Field";
import { CompanySelect } from "@/features/companies";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/input";
import { formatBytes } from "@/utils/format";
import { cn } from "@/lib/utils";
import type { JSX } from "react";

type UploadState = {
  fileCount: number;
  totalBytes: number;
  pending: boolean;
  progress: number | null;
  onUpload: () => void;
};

function uploadLabel({ fileCount, pending, progress }: UploadState): string {
  if (pending) return `Uploading… ${progress ?? 0}%`;
  return `Upload ${fileCount || ""} file${fileCount === 1 ? "" : "s"}`.replace("  ", " ");
}

function UploadButton(props: UploadState & { className?: string }): JSX.Element {
  return (
    <Button
      className={props.className}
      onClick={props.onUpload}
      disabled={props.fileCount === 0 || props.pending}
    >
      <CloudUpload /> {uploadLabel(props)}
    </Button>
  );
}

export function UploadSettings({
  companyId,
  onCompany,
  error,
  className,
  ...state
}: UploadState & {
  companyId: string;
  onCompany: (id: string) => void;
  error: string | null;
  className?: string;
}): JSX.Element {
  return (
    <Card className={className}>
      <CardContent className="space-y-4 pt-5">
        <h2 className="text-sm font-semibold">Upload settings</h2>
        <div className="grid gap-1.5">
          <Label htmlFor="up-company">Company (optional)</Label>
          <CompanySelect
            id="up-company"
            value={companyId}
            onChange={onCompany}
            allLabel="Let the assistant work it out"
            activeOnly
            disabled={state.pending}
            aria-describedby="up-company-hint"
          />
          <p id="up-company-hint" className="text-xs text-muted-foreground">
            Pick one to avoid a review step when the name on the sheet isn't exact.
          </p>
        </div>
        <p className="text-sm text-muted-foreground">
          {state.fileCount
            ? `${state.fileCount} ${state.fileCount === 1 ? "file" : "files"} · ${formatBytes(state.totalBytes)} ready to upload.`
            : "No files chosen yet."}
        </p>
        <FormError message={error} />
        <UploadButton {...state} className="w-full" />
        {state.pending ? (
          <div
            className="h-2 w-full overflow-hidden rounded-full bg-muted"
            role="progressbar"
            aria-label="Upload progress"
            aria-valuenow={state.progress ?? 0}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div
              className="h-full bg-primary transition-[width] motion-reduce:transition-none"
              style={{ width: `${state.progress ?? 0}%` }}
            />
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** Small screens: the file count and the Upload button, always in reach. */
export function MobileUploadBar({
  className,
  ...state
}: UploadState & { className?: string }): JSX.Element {
  return (
    <div
      className={cn(
        "sticky bottom-0 z-20 -mx-4 flex items-center justify-between gap-3 border-t bg-card/95 px-4 pt-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] backdrop-blur md:hidden",
        className,
      )}
    >
      <span className="tabular text-sm text-muted-foreground">
        {state.fileCount} {state.fileCount === 1 ? "file" : "files"}
      </span>
      <UploadButton {...state} />
    </div>
  );
}
