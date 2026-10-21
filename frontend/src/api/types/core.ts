// core-service types. Responses: inferred from ../schemas/core. Requests: written here,
// mirroring backend/core-service/src/schemas/ (they are never parsed at runtime).
// Decimal fields (hours, rates, money) may be sent as numbers or strings.
import type { z } from "zod";
import type {
  AuditEventReadSchema,
  BulkItemResultSchema,
  BulkResultSchema,
  CompanyReadSchema,
  DocumentReadSchema,
  EmployeeReadSchema,
  ExportBatchReadSchema,
  ExportPreviewSchema,
  ExportRowReadSchema,
  ExportTotalsReadSchema,
  FlagReadSchema,
  HolidayReadSchema,
  PrincipalReadSchema,
  ProcessingStepReadSchema,
  ReprocessRunReadSchema,
  SeverityFilterSchema,
  SortOrderSchema,
  StateChangeReadSchema,
  SubmissionReadSchema,
  SubmissionSourceSchema,
  SubmissionStateSchema,
  SubmissionStatusSchema,
  SubmissionTimelineSchema,
  TimesheetEntryReadSchema,
  TimesheetReadSchema,
  TimesheetSortSchema,
  TimesheetStatusSchema,
  WhitelistReadSchema,
} from "../schemas/core";

type Decimal = number | string;

// --- enums --------------------------------------------------------------------------
export type TimesheetStatus = z.infer<typeof TimesheetStatusSchema>;
export type SubmissionStatus = z.infer<typeof SubmissionStatusSchema>;
export type SubmissionState = z.infer<typeof SubmissionStateSchema>;
export type SubmissionSource = z.infer<typeof SubmissionSourceSchema>;
export type TimesheetSort = z.infer<typeof TimesheetSortSchema>;
export type SortOrder = z.infer<typeof SortOrderSchema>;
export type SeverityFilter = z.infer<typeof SeverityFilterSchema>;

// --- responses ----------------------------------------------------------------------
export type PrincipalRead = z.infer<typeof PrincipalReadSchema>;
export type FlagRead = z.infer<typeof FlagReadSchema>;
export type TimesheetEntryRead = z.infer<typeof TimesheetEntryReadSchema>;
export type TimesheetRead = z.infer<typeof TimesheetReadSchema>;
export type BulkItemResult = z.infer<typeof BulkItemResultSchema>;
export type BulkResult = z.infer<typeof BulkResultSchema>;
export type DocumentRead = z.infer<typeof DocumentReadSchema>;
export type SubmissionRead = z.infer<typeof SubmissionReadSchema>;
export type StateChangeRead = z.infer<typeof StateChangeReadSchema>;
export type ProcessingStepRead = z.infer<typeof ProcessingStepReadSchema>;
export type AuditEventRead = z.infer<typeof AuditEventReadSchema>;
export type ReprocessRunRead = z.infer<typeof ReprocessRunReadSchema>;
export type SubmissionTimeline = z.infer<typeof SubmissionTimelineSchema>;
export type CompanyRead = z.infer<typeof CompanyReadSchema>;
export type WhitelistRead = z.infer<typeof WhitelistReadSchema>;
export type EmployeeRead = z.infer<typeof EmployeeReadSchema>;
export type HolidayRead = z.infer<typeof HolidayReadSchema>;
export type ExportRowRead = z.infer<typeof ExportRowReadSchema>;
export type ExportTotalsRead = z.infer<typeof ExportTotalsReadSchema>;
export type ExportPreview = z.infer<typeof ExportPreviewSchema>;
export type ExportBatchRead = z.infer<typeof ExportBatchReadSchema>;

// --- requests -----------------------------------------------------------------------
export type EntryInput = {
  work_date: string;
  hours: Decimal;
  double_time_marked: boolean;
  is_holiday: boolean;
  note?: string | null;
};

export type CompanyCreate = {
  name: string;
  aliases?: string[];
  hourly_rate: Decimal;
  overtime_rate: Decimal;
  double_time_rate?: Decimal | null;
  holiday_rate: Decimal;
  currency: string;
  daily_ot_after: Decimal;
  weekly_ot_after: Decimal;
  double_time_after?: Decimal | null;
  week_start: number;
};

export type CompanyUpdate = {
  name?: string | null;
  aliases?: string[] | null;
  hourly_rate?: Decimal | null;
  overtime_rate?: Decimal | null;
  double_time_rate?: Decimal | null;
  holiday_rate?: Decimal | null;
  currency?: string | null;
  daily_ot_after?: Decimal | null;
  weekly_ot_after?: Decimal | null;
  double_time_after?: Decimal | null;
  week_start?: number | null;
  is_active?: boolean | null;
};

export type EmployeeCreate = {
  company_id: string;
  employee_code: string;
  full_name: string;
  email?: string | null;
  aliases?: string[];
  assignment_start?: string | null;
  assignment_end?: string | null;
};

export type EmployeeUpdate = {
  employee_code?: string | null;
  full_name?: string | null;
  email?: string | null;
  aliases?: string[] | null;
  assignment_start?: string | null;
  assignment_end?: string | null;
  is_active?: boolean | null;
};

export type HolidayCreate = { company_id?: string | null; holiday_date: string; name: string };
