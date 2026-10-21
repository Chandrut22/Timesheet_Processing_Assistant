// The drop area / file picker. State A (no files): it fills the whole left panel.
// State B (files chosen, `compact`): a slim bar on top of the file list.
// Keyboard: it is a button (Enter or Space opens the picker). Dropping works anywhere on
// the page (useWindowFileDrop); this area only explains it and opens the picker.
import { CloudUpload, Plus } from "lucide-react";
import { useId, useRef } from "react";
import { formatBytes } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ACCEPT, MAX_FILES } from "./upload-limits";

const TYPES = ["PDF", "PNG", "JPG", "TIFF", "DOCX", "XLSX", "CSV", "TXT"];

export function UploadDropzone({
  fileCount,
  totalBytes,
  compact,
  disabled = false,
  problems,
  onFiles,
}: {
  fileCount: number;
  totalBytes: number;
  compact: boolean;
  disabled?: boolean;
  problems: string[];
  onFiles: (files: File[]) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const limitsId = useId();
  const open = () => {
    if (!disabled) inputRef.current?.click();
  };
  const counter = (
    <span className="tabular">
      {fileCount} / {MAX_FILES} files{fileCount ? ` · ${formatBytes(totalBytes)}` : ""}
    </span>
  );

  return (
    <div className={cn("flex flex-col gap-3", compact ? "shrink-0" : "min-h-0 flex-1")}>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled || undefined}
        aria-describedby={limitsId}
        data-state={compact ? "compact" : "empty"}
        onClick={open}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            open();
          }
        }}
        className={cn(
          "rounded-lg border-2 border-dashed border-input text-center outline-none transition-colors",
          "focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 motion-reduce:transition-none",
          disabled
            ? "cursor-not-allowed opacity-60"
            : "cursor-pointer hover:border-primary/60 hover:bg-primary/5",
          compact
            ? "flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm"
            : "flex min-h-[16rem] flex-1 flex-col items-center justify-center gap-4 px-6 py-10",
        )}
      >
        {compact ? (
          <>
            <span className="flex items-center gap-2 font-medium">
              <Plus className="size-4 text-muted-foreground" aria-hidden />
              Drop more files or <span className="text-primary underline">choose files</span>
            </span>
            <span id={limitsId} className="text-muted-foreground">
              {counter}
            </span>
          </>
        ) : (
          <>
            <span className="grid size-16 place-items-center rounded-full bg-primary/10 text-primary">
              <CloudUpload className="size-8" aria-hidden />
            </span>
            <span className="text-base font-medium">
              Drag files anywhere on this page, or{" "}
              <span className="text-primary underline">choose files</span>
            </span>
            <span id={limitsId} className="text-sm text-muted-foreground">
              Up to {MAX_FILES} files, 15 MB each · {counter}
            </span>
            <span className="flex flex-wrap justify-center gap-1.5" aria-hidden>
              {TYPES.map((t) => (
                <span
                  key={t}
                  className="rounded-md border bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground"
                >
                  {t}
                </span>
              ))}
            </span>
          </>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT.join(",")}
        className="sr-only"
        tabIndex={-1}
        aria-label="Choose files to upload"
        disabled={disabled}
        onChange={(e) => {
          if (e.target.files) onFiles(Array.from(e.target.files));
          e.target.value = ""; // the same file can be picked again after removing it
        }}
      />
      <div aria-live="polite" aria-atomic="true">
        {problems.length > 0 ? (
          <ul className="space-y-1 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-left text-sm text-amber-900">
            {problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
