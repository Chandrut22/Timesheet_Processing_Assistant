// What core-service sends back. Source of truth: backend/core-service/src/schemas/.
import { z } from "zod";
import {
  RoleNameSchema,
  decimal,
  int,
  isoDate,
  isoDateTime,
  jsonObject,
  pageOf,
  uuid,
} from "./common";

// --- enums --------------------------------------------------------------------------

export const TimesheetStatusSchema = z.enum(["needs_review", "approved", "rejected", "exported"]);
export const SubmissionStatusSchema = z.enum([
  "received",
  "processing",
  "processed",
  "failed",
  "ignored",
]);
export const SubmissionStateSchema = z.enum([
  "received",
  "reading",
  "matching",
  "rule_checks",
  "awaiting_review",
  "approved",
  "rejected",
  "exported",
  "ignored",
  "failed",
  "reprocessing",
]);
export const SubmissionSourceSchema = z.enum(["email", "upload"]);
export const TimesheetSortSchema = z.enum([
  "received",
  "week",
  "employee",
  "hours",
  "gross",
  "confidence",
  "severity",
]);
export const SortOrderSchema = z.enum(["asc", "desc"]);
export const SeverityFilterSchema = z.enum(["high", "medium", "low", "none"]);

// --- who am I -----------------------------------------------------------------------

export const PrincipalReadSchema = z.object({
  id: uuid,
  role: RoleNameSchema,
  name: z.string(),
  email: z.string(),
});

// --- timesheets ---------------------------------------------------------------------

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

// --- submissions --------------------------------------------------------------------

/** How a photo / scan is written, as the vision model saw it. */
export const WritingClassSchema = z.enum([
  "printed_only",
  "handwritten_only",
  "mixed",
  "no_text",
  "uncertain",
]);

export const DocumentReadSchema = z.object({
  id: uuid,
  filename: z.string(),
  content_type: z.string(),
  size_bytes: int,
  sha256: z.string(),
  status: z.string(),
  error: z.string().nullable(),
  /** How much of a large file was read (pages / sheets); null when all of it was. */
  read_limit: z.union([jsonObject, z.string()]).nullish(),
  /** docling (typed / OCR), plain (CSV, TXT) or vision (photo / scan read by an AI model). */
  read_method: z.enum(["docling", "plain", "vision"]).nullish(),
  /** How many [UNCLEAR] marks the vision model left; 0 otherwise. */
  unclear_marks: int.nonnegative().default(0),
  /** Photos / scans only: how the page is written (null for typed documents). */
  writing_class: WritingClassSchema.nullish(),
  writing_confidence: z.number().min(0).max(1).nullish(),
  has_handwritten_hours: z.boolean().default(false),
  writing_reason: z.string().nullish(),
  created_at: isoDateTime,
});

export const SubmissionReadSchema = z.object({
  id: uuid,
  source: z.string(),
  status: z.string(),
  state: z.string(),
  state_reason: z.string().nullable(),
  company_id: uuid.nullable(),
  sender_email: z.string().nullable(),
  subject: z.string().nullable(),
  uploaded_by_id: uuid.nullable(),
  uploaded_by_name: z.string().nullable(),
  received_at: isoDateTime,
  processed_at: isoDateTime.nullable(),
  error: z.string().nullable(),
  attempts: int,
  retry_at: isoDateTime.nullable(),
  documents: z.array(DocumentReadSchema),
});
export const SubmissionPageSchema = pageOf(SubmissionReadSchema);

export const StateChangeReadSchema = z.object({
  id: uuid,
  from_state: z.string().nullable(),
  to_state: z.string(),
  reason: z.string().nullable(),
  actor_name: z.string().nullable(),
  created_at: isoDateTime,
});

export const ProcessingStepReadSchema = z.object({
  id: uuid,
  step: z.string(),
  result: z.string(),
  message: z.string(),
  document_id: uuid.nullable(),
  timesheet_id: uuid.nullable(),
  input: jsonObject,
  output: jsonObject,
  error_details: z.string().nullable(),
  duration_ms: int,
  reprocess_run_id: uuid.nullable(),
  trace_id: z.string().nullish(),
  created_at: isoDateTime,
});

export const AuditEventReadSchema = z.object({
  id: uuid,
  entity_type: z.string(),
  entity_id: uuid,
  action: z.string(),
  actor_id: uuid.nullable(),
  actor_name: z.string().nullable(),
  details: jsonObject,
  created_at: isoDateTime,
});

export const ReprocessRunReadSchema = z.object({
  id: uuid,
  submission_id: uuid,
  document_id: uuid.nullable(),
  reason: z.string(),
  requested_by_name: z.string(),
  status: z.string(),
  before_result: jsonObject,
  after_result: jsonObject.nullable(),
  error: z.string().nullable(),
  created_at: isoDateTime,
  completed_at: isoDateTime.nullable(),
});

export const SubmissionTimelineSchema = z.object({
  submission: SubmissionReadSchema,
  states: z.array(StateChangeReadSchema),
  steps: z.array(ProcessingStepReadSchema),
  audit: z.array(AuditEventReadSchema),
  reprocess_runs: z.array(ReprocessRunReadSchema),
});

// --- master data --------------------------------------------------------------------

export const CompanyReadSchema = z.object({
  id: uuid,
  name: z.string(),
  aliases: z.array(z.string()),
  hourly_rate: decimal,
  overtime_rate: decimal,
  double_time_rate: decimal.nullable(),
  holiday_rate: decimal,
  currency: z.string(),
  daily_ot_after: decimal,
  weekly_ot_after: decimal,
  double_time_after: decimal.nullable(),
  week_start: int,
  is_active: z.boolean(),
  created_at: isoDateTime,
  updated_at: isoDateTime,
});
export const CompanyPageSchema = pageOf(CompanyReadSchema);

export const WhitelistReadSchema = z.object({
  id: uuid,
  company_id: uuid,
  kind: z.string(),
  value: z.string(),
  created_at: isoDateTime,
});

export const EmployeeReadSchema = z.object({
  id: uuid,
  company_id: uuid,
  employee_code: z.string(),
  full_name: z.string(),
  email: z.string().nullable(),
  aliases: z.array(z.string()),
  assignment_start: isoDate.nullable(),
  assignment_end: isoDate.nullable(),
  is_active: z.boolean(),
  created_at: isoDateTime,
  updated_at: isoDateTime,
});
export const EmployeePageSchema = pageOf(EmployeeReadSchema);

export const HolidayReadSchema = z.object({
  id: uuid,
  company_id: uuid.nullable(),
  holiday_date: isoDate,
  name: z.string(),
  /** Inactive holidays stay listed but no longer count when pay is calculated. */
  is_active: z.boolean(),
  created_at: isoDateTime,
});

// --- payroll export -----------------------------------------------------------------

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

export const DashboardSnapshotSchema = z.object({
  counts: z.object({
    needs_review: z.number().int(),
    high_severity: z.number().int(),
    approved_waiting_export: z.number().int(),
    failed_submissions: z.number().int(),
  }),
  recent: z.array(SubmissionReadSchema),
});
export type DashboardSnapshot = z.infer<typeof DashboardSnapshotSchema>;
