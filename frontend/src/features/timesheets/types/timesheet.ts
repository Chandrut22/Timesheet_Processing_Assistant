import { z } from "zod";
import { decimal, int, isoDate, isoDateTime, pageOf, uuid } from "@/services/schemas";
import type { SubmissionState } from "@/features/submissions";
import type { SortOrder, Decimal } from "@/types/api";

export const TimesheetStatusSchema = z.enum(["needs_review", "approved", "rejected", "exported"]);

export const TimesheetSortSchema = z.enum([
  "received",
  "week",
  "employee",
  "hours",
  "gross",
  "confidence",
  "severity",
]);

export const SeverityFilterSchema = z.enum(["high", "medium", "low", "none"]);

/** Flags may carry extra keys (e.g. which people are missing), so unknown keys are kept. */
export const FlagReadSchema = z.looseObject({
  code: z.string(),
  message: z.string(),
  severity: z.string(),
});

/** One day. Days are stored on the timesheet and known by their date (no id). */
export const TimesheetEntryReadSchema = z.object({
  work_date: isoDate,
  hours: decimal,
  is_holiday: z.boolean(),
  sheet_holiday: z.boolean(),
  double_time_marked: z.boolean(),
  note: z.string().nullable(),
});

export const TimesheetReadSchema = z.object({
  id: uuid,
  submission_id: uuid,
  document_id: uuid.nullable(),
  company_id: uuid.nullable(),
  employee_id: uuid.nullable(),
  extracted_name: z.string().nullable(),
  extracted_code: z.string().nullable(),
  extracted_company_name: z.string().nullable(),
  week_start: isoDate.nullable(),
  status: z.string(),
  version: int,
  reprocess_run_id: uuid.nullable(),
  regular_hours: decimal,
  overtime_hours: decimal,
  double_time_hours: decimal,
  holiday_hours: decimal,
  total_hours: decimal,
  stated_total: decimal.nullable(),
  email_stated_total: decimal.nullable(),
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
  read_confidence: z.number().nullable(),
  confidence: z.number().nullable(),
  match_method: z.string().nullable(),
  match_reason: z.string().nullable(),
  flags: z.array(FlagReadSchema),
  severity: z.string().nullable(),
  notes: z.string().nullable(),
  reviewed_by_name: z.string().nullable(),
  reviewed_at: isoDateTime.nullable(),
  created_at: isoDateTime,
  entries: z.array(TimesheetEntryReadSchema),
});

export const TimesheetPageSchema = pageOf(TimesheetReadSchema);

/** What made the next version of a timesheet (only data changes make versions). */
export const TimesheetChangeSchema = z.enum([
  "entries_edited",
  "employee_matched",
  "week_changed",
  "recalculated",
  "reprocessed",
  "rolled_back",
]);

/** GET /timesheets/{id}/versions: newest first; the first one is the current timesheet. */
export const TimesheetVersionSummarySchema = z.object({
  version: int,
  current: z.boolean(),
  change: TimesheetChangeSchema.nullable(),
  changed_by_name: z.string().nullable(),
  changed_at: isoDateTime.nullable(),
  reason: z.string().nullable(),
  reprocess_run_id: uuid.nullable(),
  employee_id: uuid.nullable(),
  extracted_name: z.string().nullable(),
  week_start: isoDate.nullable(),
  status: z.string().nullable(),
  days: int,
  total_hours: decimal,
  gross_amount: decimal.nullable(),
  flags: z.array(z.string()),
});

/** GET /timesheets/{id}/versions/{n}: one version with its days and pay. */
export const TimesheetVersionReadSchema = TimesheetVersionSummarySchema.extend({
  entries: z.array(TimesheetEntryReadSchema),
  regular_hours: decimal,
  overtime_hours: decimal,
  double_time_hours: decimal,
  holiday_hours: decimal,
  stated_total: decimal.nullable(),
  currency: z.string().nullable(),
  match_method: z.string().nullable(),
  match_reason: z.string().nullable(),
  notes: z.string().nullable(),
});

export const BulkItemResultSchema = z.object({
  timesheet_id: uuid,
  ok: z.boolean(),
  status: z.string().nullish(),
  error: z.string().nullish(),
});

export const BulkResultSchema = z.object({
  requested: int,
  succeeded: int,
  failed: int,
  results: z.array(BulkItemResultSchema),
});

export type TimesheetStatus = z.infer<typeof TimesheetStatusSchema>;

export type TimesheetSort = z.infer<typeof TimesheetSortSchema>;

export type SeverityFilter = z.infer<typeof SeverityFilterSchema>;

export type FlagRead = z.infer<typeof FlagReadSchema>;

export type TimesheetEntryRead = z.infer<typeof TimesheetEntryReadSchema>;

export type TimesheetRead = z.infer<typeof TimesheetReadSchema>;

export type TimesheetChange = z.infer<typeof TimesheetChangeSchema>;

export type TimesheetVersionSummary = z.infer<typeof TimesheetVersionSummarySchema>;

export type TimesheetVersionRead = z.infer<typeof TimesheetVersionReadSchema>;

export type BulkItemResult = z.infer<typeof BulkItemResultSchema>;

export type BulkResult = z.infer<typeof BulkResultSchema>;

export type EntryInput = {
  work_date: string;
  hours: Decimal;
  double_time_marked: boolean;
  is_holiday: boolean;
  note?: string | null;
};

export const TIMESHEET_STATUSES: TimesheetStatus[] = [
  "needs_review",
  "approved",
  "rejected",
  "exported",
];

export const TIMESHEET_SORTS: TimesheetSort[] = [
  "received",
  "week",
  "employee",
  "hours",
  "gross",
  "confidence",
  "severity",
];

export const SEVERITIES: SeverityFilter[] = ["high", "medium", "low", "none"];

export type TimesheetListParams = {
  status?: TimesheetStatus[];
  state?: SubmissionState[];
  severity?: SeverityFilter[];
  flag?: string;
  submission_id?: string;
  company_id?: string;
  employee_id?: string;
  matched?: boolean;
  sender?: string;
  q?: string;
  date_from?: string;
  date_to?: string;
  received_from?: string;
  received_to?: string;
  min_confidence?: number;
  max_confidence?: number;
  sort?: TimesheetSort;
  order?: SortOrder;
  page?: number;
  size?: number;
};
