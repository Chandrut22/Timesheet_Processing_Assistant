// The review queue keeps every filter in the URL, so a reload or a shared link
// shows the same list. This file parses the URL safely and turns it into API params.
import type { TimesheetListParams } from "@/api/core";
import {
  SEVERITIES,
  TIMESHEET_SORTS,
  TIMESHEET_STATUSES,
  type SeverityFilter,
  type SortOrder,
  type TimesheetSort,
  type TimesheetStatus,
} from "@/api/models";

export type ReviewSearch = {
  status?: TimesheetStatus | "all";
  severity?: SeverityFilter;
  flag?: string;
  company_id?: string;
  employee_id?: string;
  matched?: "yes" | "no";
  sender?: string;
  q?: string;
  date_from?: string;
  date_to?: string;
  received_from?: string;
  received_to?: string;
  /** Percent, 0–100 (the API wants 0–1). */
  min_conf?: number;
  max_conf?: number;
  superseded?: boolean;
  sort?: TimesheetSort;
  order?: SortOrder;
  page?: number;
  size?: number;
};

export const REVIEW_DEFAULTS = {
  status: "needs_review" as const,
  sort: "severity" as TimesheetSort,
  order: "desc" as SortOrder,
  page: 1,
  size: 25,
};

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const str = (v: unknown, max = 255): string | undefined =>
  typeof v === "string" && v.trim() ? v.trim().slice(0, max) : typeof v === "number" ? String(v) : undefined;
const oneOf = <T extends string>(v: unknown, values: readonly T[]): T | undefined =>
  typeof v === "string" && (values as readonly string[]).includes(v) ? (v as T) : undefined;
const date = (v: unknown) => (typeof v === "string" && ISO_DATE.test(v) ? v : undefined);
const uuid = (v: unknown) => (typeof v === "string" && UUID.test(v) ? v : undefined);
const int = (v: unknown, min: number, max: number): number | undefined => {
  const n = typeof v === "number" ? v : typeof v === "string" ? Number(v) : NaN;
  return Number.isInteger(n) && n >= min && n <= max ? n : undefined;
};
const bool = (v: unknown) => (v === true || v === "true" ? true : undefined);

export function parseReviewSearch(s: Record<string, unknown>): ReviewSearch {
  return {
    status: s.status === "all" ? "all" : oneOf(s.status, TIMESHEET_STATUSES),
    severity: oneOf(s.severity, SEVERITIES),
    flag: str(s.flag, 50),
    company_id: uuid(s.company_id),
    employee_id: uuid(s.employee_id),
    matched: oneOf(s.matched, ["yes", "no"] as const),
    sender: str(s.sender),
    q: str(s.q, 100),
    date_from: date(s.date_from),
    date_to: date(s.date_to),
    received_from: date(s.received_from),
    received_to: date(s.received_to),
    min_conf: int(s.min_conf, 0, 100),
    max_conf: int(s.max_conf, 0, 100),
    superseded: bool(s.superseded),
    sort: oneOf(s.sort, TIMESHEET_SORTS),
    order: oneOf(s.order, ["asc", "desc"] as const),
    page: int(s.page, 1, 10_000),
    size: int(s.size, 1, 100),
  };
}

export function reviewParams(s: ReviewSearch): TimesheetListParams {
  const status = s.status ?? REVIEW_DEFAULTS.status;
  return {
    status: status === "all" ? undefined : [status],
    severity: s.severity ? [s.severity] : undefined,
    flag: s.flag,
    company_id: s.company_id,
    employee_id: s.employee_id,
    matched: s.matched === "yes" ? true : s.matched === "no" ? false : undefined,
    sender: s.sender,
    q: s.q,
    date_from: s.date_from,
    date_to: s.date_to,
    received_from: s.received_from,
    received_to: s.received_to,
    min_confidence: s.min_conf !== undefined ? s.min_conf / 100 : undefined,
    max_confidence: s.max_conf !== undefined ? s.max_conf / 100 : undefined,
    include_superseded: s.superseded || undefined,
    sort: s.sort ?? REVIEW_DEFAULTS.sort,
    order: s.order ?? REVIEW_DEFAULTS.order,
    page: s.page ?? REVIEW_DEFAULTS.page,
    size: s.size ?? REVIEW_DEFAULTS.size,
  };
}

/** How many filters beyond the defaults are on (for the "More filters" badge). */
export function advancedFilterCount(s: ReviewSearch): number {
  return [
    s.flag,
    s.sender,
    s.employee_id,
    s.date_from,
    s.date_to,
    s.received_from,
    s.received_to,
    s.min_conf,
    s.max_conf,
    s.superseded,
  ].filter((v) => v !== undefined).length;
}
