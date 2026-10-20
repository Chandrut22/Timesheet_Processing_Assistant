// Friendly names for the generated API types. Never write API models by hand:
// run `npm run gen:api` and import from here.
import type { components as Core } from "./types/core";
import type { components as Auth } from "./types/auth";

type C = Core["schemas"];
type A = Auth["schemas"];

export type Page<T> = { items: T[]; total: number; page: number; size: number };

export type RoleName = C["RoleName"];
export type PrincipalRead = C["PrincipalRead"];

export type TimesheetRead = C["TimesheetRead"];
export type TimesheetEntryRead = C["TimesheetEntryRead"];
export type TimesheetStatus = C["TimesheetStatus"];
export type TimesheetSort = C["TimesheetSort"];
export type SortOrder = C["SortOrder"];
export type SeverityFilter = C["SeverityFilter"];
export type FlagRead = C["FlagRead"];
export type EntryInput = C["EntryInput"];
export type BulkResult = C["BulkResult"];
export type BulkItemResult = C["BulkItemResult"];

export type SubmissionRead = C["SubmissionRead"];
export type SubmissionStatus = C["SubmissionStatus"];
export type SubmissionState = C["SubmissionState"];
export type SubmissionSource = C["SubmissionSource"];
export type SubmissionTimeline = C["SubmissionTimeline"];
export type StateChangeRead = C["StateChangeRead"];
export type ProcessingStepRead = C["ProcessingStepRead"];
export type ReprocessRunRead = C["ReprocessRunRead"];
export type DocumentRead = C["DocumentRead"];
export type AuditEventRead = C["AuditEventRead"];

export type CompanyRead = C["CompanyRead"];
export type CompanyCreate = C["CompanyCreate"];
export type CompanyUpdate = C["CompanyUpdate"];
export type WhitelistRead = C["WhitelistRead"];
export type EmployeeRead = C["EmployeeRead"];
export type EmployeeCreate = C["EmployeeCreate"];
export type EmployeeUpdate = C["EmployeeUpdate"];
export type HolidayRead = C["HolidayRead"];
export type HolidayCreate = C["HolidayCreate"];

export type ExportPreview = C["ExportPreview"];
export type ExportRowRead = C["ExportRowRead"];
export type ExportBatchRead = C["ExportBatchRead"];

export type TokenResponse = A["TokenResponse"];
export type MessageResponse = A["MessageResponse"];
export type UserRead = A["UserRead"];
export type UserCreate = A["UserCreate"];
export type UserUpdate = A["UserUpdate"];

export const TIMESHEET_STATUSES: TimesheetStatus[] = [
  "needs_review",
  "approved",
  "rejected",
  "exported",
  "superseded",
];
export const SUBMISSION_STATUSES: SubmissionStatus[] = [
  "received",
  "processing",
  "processed",
  "failed",
  "ignored",
];
export const SUBMISSION_STATES: SubmissionState[] = [
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
