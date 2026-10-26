import type { TimesheetListParams } from "../types/timesheet";

/** Query keys for timesheets: invalidate `timesheetKeys.all` after any change. */
export const timesheetKeys = {
  all: ["timesheets"] as const,
  list: (p: TimesheetListParams) => ["timesheets", "list", p] as const,
  detail: (id: string) => ["timesheets", "detail", id] as const,
  versions: (id: string) => ["timesheets", "versions", id] as const,
  version: (id: string, n: number) => ["timesheets", "versions", id, n] as const,
};
