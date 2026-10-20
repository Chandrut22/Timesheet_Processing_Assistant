import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileUp, Trash2, CloudUpload } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { toast } from "sonner";
import { coreApi } from "@/api/core";
import { errorMessage } from "@/api/errors";
import { qk } from "@/api/queryKeys";
import { CompanySelect } from "@/components/CompanySelect";
import { FormError } from "@/components/Field";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/input";
import { formatBytes } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/upload")({ component: UploadPage });

const MAX_FILES = 10;
const MAX_BYTES = 15 * 1024 * 1024;
const ACCEPT = [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".docx", ".xlsx", ".csv", ".txt"];

function extOf(name: string) {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
}

function UploadPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [problems, setProblems] = useState<string[]>([]);
  const [companyId, setCompanyId] = useState("");
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);

  const addFiles = (incoming: FileList | File[]) => {
    const next = [...files];
    const issues: string[] = [];
    for (const f of Array.from(incoming)) {
      if (next.some((x) => x.name === f.name && x.size === f.size)) continue;
      if (!ACCEPT.includes(extOf(f.name))) {
        issues.push(`${f.name}: this file type isn't supported.`);
        continue;
      }
      if (f.size > MAX_BYTES) {
        issues.push(`${f.name}: larger than 15 MB.`);
        continue;
      }
      if (next.length >= MAX_FILES) {
        issues.push(`${f.name}: you can upload at most ${MAX_FILES} files at once.`);
        continue;
      }
      next.push(f);
    }
    setFiles(next);
    setProblems(issues);
  };

  const upload = useMutation({
    mutationFn: () => coreApi.upload(files, companyId || undefined, setProgress),
    meta: { silentError: true },
    onSuccess: (submission) => {
      toast.success("Uploaded. Processing has started.");
      void queryClient.invalidateQueries({ queryKey: qk.submissions.all });
      void navigate({ to: "/submissions/$submissionId", params: { submissionId: submission.id } });
    },
    onSettled: () => setProgress(null),
  });

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  };

  return (
    <>
      <PageHeader
        title="Upload timesheets"
        description="For timesheets that didn't arrive by email. They go through the same reading and checks."
      />
      <Card className="max-w-3xl">
        <CardContent className="space-y-5 pt-5">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={cn(
              "flex flex-col items-center gap-3 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors",
              dragging ? "border-primary bg-primary/5" : "border-input",
            )}
          >
            <CloudUpload className="size-8 text-muted-foreground" aria-hidden />
            <div>
              <p className="text-sm font-medium">Drag files here, or</p>
              <Button variant="link" className="h-auto p-0" onClick={() => inputRef.current?.click()}>
                choose files
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Up to {MAX_FILES} files, 15 MB each · PDF, images (PNG, JPG, TIFF), DOCX, XLSX, CSV, TXT
            </p>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={ACCEPT.join(",")}
              className="sr-only"
              aria-label="Choose files to upload"
              onChange={(e) => {
                if (e.target.files) addFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </div>

          {problems.length > 0 ? (
            <ul role="alert" className="space-y-1 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              {problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          ) : null}

          {files.length > 0 ? (
            <ul className="divide-y rounded-md border">
              {files.map((f, i) => (
                <li key={`${f.name}-${f.size}`} className="flex items-center gap-3 px-3 py-2 text-sm">
                  <FileUp className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                  <span className="min-w-0 flex-1 truncate">{f.name}</span>
                  <span className="tabular text-xs text-muted-foreground">{formatBytes(f.size)}</span>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Remove ${f.name}`}
                    disabled={upload.isPending}
                    onClick={() => setFiles(files.filter((_, j) => j !== i))}
                  >
                    <Trash2 />
                  </Button>
                </li>
              ))}
            </ul>
          ) : null}

          <div className="grid max-w-sm gap-1.5">
            <Label htmlFor="up-company">Company (optional)</Label>
            <CompanySelect
              id="up-company"
              value={companyId}
              onChange={setCompanyId}
              allLabel="Let the assistant work it out"
              activeOnly
              aria-describedby="up-company-hint"
            />
            <p id="up-company-hint" className="text-xs text-muted-foreground">
              Pick one to avoid a review step when the name on the sheet isn't exact.
            </p>
          </div>

          <FormError message={upload.error ? errorMessage(upload.error) : null} />

          <div className="flex items-center gap-3">
            <Button onClick={() => upload.mutate()} disabled={files.length === 0 || upload.isPending}>
              <CloudUpload /> {upload.isPending ? `Uploading… ${progress ?? 0}%` : `Upload ${files.length || ""} file${files.length === 1 ? "" : "s"}`}
            </Button>
            {progress !== null ? (
              <div className="h-2 w-40 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
                <div className="h-full bg-primary transition-[width]" style={{ width: `${progress}%` }} />
              </div>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </>
  );
}
