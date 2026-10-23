// Types shared by both services. Response types are inferred from the zod schemas in
// ../schemas, so a type and its runtime check can never disagree.
import type { z } from "zod";
import type {
  BulkDeleteResultSchema,
  BulkStatusItemSchema,
  BulkStatusResultSchema,
  CellErrorSchema,
  ImportReportSchema,
  OnDuplicateSchema,
  OnErrorSchema,
  RoleNameSchema,
  RowResultSchema,
} from "../schemas/common";

export type Page<T> = { items: T[]; total: number; page: number; size: number };

export type RoleName = z.infer<typeof RoleNameSchema>;

export type BulkStatusItem = z.infer<typeof BulkStatusItemSchema>;
export type BulkStatusResult = z.infer<typeof BulkStatusResultSchema>;
export type BulkDeleteResult = z.infer<typeof BulkDeleteResultSchema>;

export type CellError = z.infer<typeof CellErrorSchema>;
export type RowResult = z.infer<typeof RowResultSchema>;
export type ImportReport = z.infer<typeof ImportReportSchema>;
export type OnError = z.infer<typeof OnErrorSchema>;
export type OnDuplicate = z.infer<typeof OnDuplicateSchema>;

/** The query options of POST /{resource}/import. */
export type ImportOptions = { dryRun: boolean; onError: OnError; onDuplicate: OnDuplicate };

/** The admin resources that can be imported from a CSV / XLSX file. */
export type ImportResource = "users" | "employees" | "companies" | "holidays";
