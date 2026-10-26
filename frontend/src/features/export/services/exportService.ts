import { cleanParams, filenameFromDisposition, http, saveBlob } from "@/lib/axios";
import {
  ExportBatchPageSchema,
  ExportBatchReadSchema,
  ExportPreviewSchema,
  type ExportBatchRead,
  type ExportFormat,
  type ExportListParams,
} from "../types/export";
import { checked } from "@/services/response";

/** The name to save a download under when the server sends none: the batch's file
 * name with the extension of the chosen format ("payroll_acme_2026-09-07_ab12cd34.xlsx"). */
export function exportFileName(
  batch: Pick<ExportBatchRead, "id" | "filename">,
  format: ExportFormat,
): string {
  const base = (batch.filename || `payroll-${batch.id}`).replace(/\.(csv|xlsx)$/i, "");
  return `${base}.${format}`;
}

export const exportService = {
  previewExport: (companyId: string, weekStart: string) =>
    checked(
      ExportPreviewSchema,
      http.get("/api/exports/preview", {
        params: { company_id: companyId, week_start: weekStart },
      }),
    ),
  createExport: (companyId: string, weekStart: string, allowPending: boolean) =>
    checked(
      ExportBatchReadSchema,
      http.post("/api/exports", {
        company_id: companyId,
        week_start: weekStart,
        allow_pending: allowPending,
      }),
    ),
  listExports: (params: ExportListParams) =>
    checked(ExportBatchPageSchema, http.get("/api/exports", { params: cleanParams(params) })),
  /** Saves the payroll sheet as CSV (default) or Excel. Both hold the same rows. */
  downloadExport: async (
    batch: Pick<ExportBatchRead, "id" | "filename">,
    format: ExportFormat = "csv",
  ) => {
    const res = await http.get<Blob>(`/api/exports/${batch.id}/download`, {
      params: { format },
      responseType: "blob",
    });
    const name =
      filenameFromDisposition(res.headers["content-disposition"]) || exportFileName(batch, format);
    saveBlob(res.data, name);
  },
};
