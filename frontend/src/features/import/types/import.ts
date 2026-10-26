import { z } from "zod";
import { int } from "@/services/schemas";

export const OnErrorSchema = z.enum(["abort", "skip"]);

export const OnDuplicateSchema = z.enum(["error", "skip", "update"]);

export const RowStatusSchema = z.enum(["created", "updated", "skipped", "failed"]);

export const CellErrorSchema = z.object({ column: z.string().nullable(), message: z.string() });

export const RowResultSchema = z.object({
  row: int,
  status: RowStatusSchema,
  errors: z.array(CellErrorSchema),
  warnings: z.array(z.string()),
});

export const ImportReportSchema = z.object({
  resource: z.string(),
  file_name: z.string(),
  dry_run: z.boolean(),
  committed: z.boolean(),
  on_error: OnErrorSchema,
  on_duplicate: OnDuplicateSchema,
  total_rows: int,
  created: int,
  updated: int,
  skipped: int,
  failed: int,
  warnings: z.array(z.string()),
  rows: z.array(RowResultSchema),
  rows_omitted: int,
});

export type CellError = z.infer<typeof CellErrorSchema>;

export type RowResult = z.infer<typeof RowResultSchema>;

export type ImportReport = z.infer<typeof ImportReportSchema>;

export type OnError = z.infer<typeof OnErrorSchema>;

export type OnDuplicate = z.infer<typeof OnDuplicateSchema>;

/** The query options of POST /{resource}/import. */
export type ImportOptions = { dryRun: boolean; onError: OnError; onDuplicate: OnDuplicate };

/** The admin resources that can be imported from a CSV / XLSX file. */
export type ImportResource = "users" | "employees" | "companies" | "holidays";
