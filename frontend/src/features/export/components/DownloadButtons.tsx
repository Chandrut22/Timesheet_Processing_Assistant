// "Download CSV" and "Download Excel (.xlsx)" for one payroll export. Both files hold the
// same rows (the workbook is built from the CSV stored with the export). Each button
// shows its own busy state; a failure (expired session, rate limit, server error)
// becomes a toast with the shared client's message.
import { Download, FileSpreadsheet } from "lucide-react";
import { useState, type JSX } from "react";
import { toast } from "sonner";
import { errorMessage } from "@/services/apiErrors";
import type { ExportBatchRead, ExportFormat } from "../types/export";
import { Button } from "@/components/ui/button";
import { exportService } from "../services/exportService";

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
  const [busy, setBusy] = useState<Partial<Record<ExportFormat, boolean>>>({});

  const download = async (format: ExportFormat): Promise<void> => {
    setBusy((b) => ({ ...b, [format]: true }));
    try {
      await exportService.downloadExport(batch, format);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy((b) => ({ ...b, [format]: false }));
    }
  };

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
