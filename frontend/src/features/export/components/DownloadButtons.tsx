// "Download CSV" and "Download Excel (.xlsx)" for one payroll export. Both files hold the
// same rows (the workbook is built from the CSV stored with the export). Each button
// shows its own busy state; a failure (expired session, rate limit, server error)
// becomes a toast with the shared client's message.
import { Download, FileSpreadsheet } from "lucide-react";
import { type JSX } from "react";
import type { ExportBatchRead, ExportFormat } from "../types/export";
import { Button } from "@/components/ui/button";
import { useDownloadExport } from "../hooks/useExportActions";

const FORMATS: { format: ExportFormat; label: string; icon: typeof Download }[] = [
  { format: "csv", label: "Download CSV", icon: Download },
  { format: "xlsx", label: "Download Excel (.xlsx)", icon: FileSpreadsheet },
];

export function DownloadButtons({
  batch,
  size = "sm",
}: {
  batch: Pick<ExportBatchRead, "id" | "filename">;
  size?: "sm" | "default";
}): JSX.Element {
  const { download, busy } = useDownloadExport(batch);

  return (
    <div
      role="group"
      aria-label={`Download ${batch.filename}`}
      className="inline-flex flex-wrap gap-1.5"
    >
      {FORMATS.map(({ format, label, icon: Icon }) => (
        <Button
          key={format}
          variant="outline"
          size={size}
          disabled={busy[format]}
          aria-busy={busy[format] || undefined}
          onClick={() => void download(format)}
        >
          <Icon /> {busy[format] ? "Downloading…" : label}
        </Button>
      ))}
    </div>
  );
}
