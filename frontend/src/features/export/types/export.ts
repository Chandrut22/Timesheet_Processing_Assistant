import { z } from "zod";
import { decimal, int, isoDate, isoDateTime, pageOf, uuid } from "@/services/schemas";

export const ExportRowReadSchema = z.object({
  timesheet_id: uuid,
  employee_id: uuid,
  employee_code: z.string(),
  employee_name: z.string(),
  regular_hours: decimal,
  overtime_hours: decimal,
  double_time_hours: decimal,
  holiday_hours: decimal,
  total_hours: decimal,
  currency: z.string().nullable(),
  hourly_rate: decimal.nullable(),
  overtime_rate: decimal.nullable(),
  double_time_rate: decimal.nullable(),
  holiday_rate: decimal.nullable(),
  regular_amount: decimal.nullable(),
  overtime_amount: decimal.nullable(),
  double_time_amount: decimal.nullable(),
  holiday_amount: decimal.nullable(),
  gross_amount: decimal.nullable(),
  approved_by: z.string().nullable(),
  approved_at: isoDateTime.nullable(),
});

export const ExportTotalsReadSchema = z.object({
  rows: int,
  regular_hours: decimal,
  overtime_hours: decimal,
  double_time_hours: decimal,
  holiday_hours: decimal,
  total_hours: decimal,
  regular_amount: decimal,
  overtime_amount: decimal,
  double_time_amount: decimal,
  holiday_amount: decimal,
  gross_amount: decimal,
  unpriced: int,
});

export const ExportPreviewSchema = z.object({
  company_id: uuid,
  company_name: z.string(),
  week_start: isoDate,
  week_end: isoDate,
  currency: z.string(),
  rows: z.array(ExportRowReadSchema),
  totals: ExportTotalsReadSchema,
  pending_review: int,
  rejected: int,
  already_exported: int,
  problems: z.array(z.string()),
});

export const ExportBatchReadSchema = z.object({
  id: uuid,
  company_id: uuid,
  company_name: z.string(),
  week_start: isoDate,
  week_end: isoDate,
  row_count: int,
  regular_hours: decimal,
  overtime_hours: decimal,
  double_time_hours: decimal,
  holiday_hours: decimal,
  currency: z.string(),
  regular_amount: decimal,
  overtime_amount: decimal,
  double_time_amount: decimal,
  holiday_amount: decimal,
  gross_amount: decimal,
  filename: z.string(),
  created_by_name: z.string().nullable(),
  created_at: isoDateTime,
});

export const ExportBatchPageSchema = pageOf(ExportBatchReadSchema);

/** File format of a payroll export download (GET /exports/{id}/download?format=). */
export type ExportFormat = "csv" | "xlsx";

export type ExportRowRead = z.infer<typeof ExportRowReadSchema>;

export type ExportTotalsRead = z.infer<typeof ExportTotalsReadSchema>;

export type ExportPreview = z.infer<typeof ExportPreviewSchema>;

export type ExportBatchRead = z.infer<typeof ExportBatchReadSchema>;

export type ExportListParams = {
  company_id?: string;
  week_start?: string;
  page?: number;
  size?: number;
};
