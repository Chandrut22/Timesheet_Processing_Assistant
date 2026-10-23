// Friendly names for the API types, in one place for the screens to import from.
// The types are hand-written in ./types (responses inferred from the zod schemas in
// ./schemas); see the README, "Keeping types in sync", when the backend changes.
export type * from "./types/common";
export type * from "./types/auth";
export type * from "./types/core";

import type {
  SeverityFilter,
  SubmissionState,
  SubmissionStatus,
  TimesheetSort,
  TimesheetStatus,
} from "./types/core";

export const TIMESHEET_STATUSES: TimesheetStatus[] = [
  "needs_review",
  "approved",
  "rejected",
  "exported",
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
