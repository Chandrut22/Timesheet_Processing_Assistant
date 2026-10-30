import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { toast } from "sonner";

import { timesheetKeys } from "@/features/timesheets";
import type { MutationCallbacks } from "@/hooks/mutationOptions";
import { errorMessage } from "@/utils/errors";

import { exportKeys } from "../queries/exportQueries";
import { exportService } from "../services/exportService";
import type { ExportBatchRead, ExportFormat } from "../types/export";

/** Create the payroll sheet for one company and week. Its timesheets become exported,
 * so the timesheet lists are refreshed too. The page shows the error itself. */
export function useCreateExport(
  companyId: string,
  week: string,
  opts: MutationCallbacks<ExportBatchRead, boolean> = {},
): UseMutationResult<ExportBatchRead, Error, boolean> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (allowPending: boolean) =>
      exportService.createExport(companyId, week, allowPending),
    meta: { silentError: true },
    onSuccess: (batch, allowPending) => {
      void queryClient.invalidateQueries({ queryKey: exportKeys.all });
      void queryClient.invalidateQueries({ queryKey: timesheetKeys.all });
      opts.onSuccess?.(batch, allowPending);
    },
  });
}

export type ExportDownload = {
  download: (format: ExportFormat) => Promise<void>;
  /** Each format has its own busy state (both buttons can run at once). */
  busy: Partial<Record<ExportFormat, boolean>>;
};

/** Download one export as CSV or Excel. A failure (expired session, rate limit,
 * server error) becomes a toast with the shared client's message. */
export function useDownloadExport(batch: Pick<ExportBatchRead, "id" | "filename">): ExportDownload {
  const [busy, setBusy] = useState<Partial<Record<ExportFormat, boolean>>>({});
  const download = useCallback(
    async (format: ExportFormat): Promise<void> => {
      setBusy((b) => ({ ...b, [format]: true }));
      try {
        await exportService.downloadExport(batch, format);
      } catch (err) {
        toast.error(errorMessage(err));
      } finally {
        setBusy((b) => ({ ...b, [format]: false }));
      }
    },
    [batch],
  );
  return { download, busy };
}
