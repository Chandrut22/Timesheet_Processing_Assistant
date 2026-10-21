// The chosen files: one row each (type icon, name, size, remove), with a header that
// totals them and clears the list. Everything is disabled while the upload runs.
import {
  File as FileIcon,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileType,
  Trash2,
  X,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/format";
import { fileKind, totalBytes, type FileKind } from "./upload-limits";

const ICONS: Record<FileKind, LucideIcon> = {
  pdf: FileType,
  image: FileImage,
  word: FileText,
  excel: FileSpreadsheet,
  text: FileText,
  other: FileIcon,
};

export function SelectedFiles({
  files,
  disabled = false,
  onRemove,
  onClear,
}: {
  files: File[];
  disabled?: boolean;
  onRemove: (index: number) => void;
  onClear: () => void;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b bg-muted/40 px-3 py-2 text-sm">
        <span className="tabular font-medium">
          {files.length} {files.length === 1 ? "file" : "files"} · {formatBytes(totalBytes(files))}
        </span>
        <Button variant="ghost" size="sm" disabled={disabled} onClick={onClear}>
          <X /> Clear all
        </Button>
      </div>
      <ul className="min-h-0 flex-1 divide-y overflow-y-auto" aria-label="Files to upload">
        {files.map((f, i) => {
          const Icon = ICONS[fileKind(f.name)];
          return (
            <li key={`${f.name}-${f.size}`} className="flex items-center gap-3 px-3 py-2 text-sm">
              <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
              <span className="min-w-0 flex-1 truncate" title={f.name}>
                {f.name}
              </span>
              <span className="tabular shrink-0 text-xs text-muted-foreground">
                {formatBytes(f.size)}
              </span>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Remove ${f.name}`}
                disabled={disabled}
                onClick={() => onRemove(i)}
              >
                <Trash2 />
              </Button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
