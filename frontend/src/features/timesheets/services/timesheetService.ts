import { cleanParams, http } from "@/lib/axios";
import {
  BulkResultSchema,
  TimesheetPageSchema,
  TimesheetReadSchema,
  TimesheetVersionReadSchema,
  TimesheetVersionSummarySchema,
  type EntryInput,
  type TimesheetListParams,
} from "../types/timesheet";
import { z } from "zod";
import { checked } from "@/services/response";

export const timesheetService = {
  /** `signal` lets TanStack Query cancel a search that a newer one replaced. */
  listTimesheets: (params: TimesheetListParams, signal?: AbortSignal) =>
    checked(
      TimesheetPageSchema,
      http.get("/api/timesheets", { params: cleanParams(params), signal }),
    ),
  getTimesheet: (id: string) => checked(TimesheetReadSchema, http.get(`/api/timesheets/${id}`)),
  /**
   * Replace the days. Saved in the current version; with newVersion ("Create as new
   * version") the timesheet as it was is kept in the history and this becomes the next.
   */
  updateEntries: (id: string, entries: EntryInput[], newVersion = false) =>
    checked(
      TimesheetReadSchema,
      http.patch(`/api/timesheets/${id}/entries`, { entries, new_version: newVersion }),
    ),
  /** Move a weekly-total timesheet (no days) to another week (a company week-start day). */
  setWeek: (id: string, weekStart: string, newVersion = false) =>
    checked(
      TimesheetReadSchema,
      http.patch(`/api/timesheets/${id}/week`, { week_start: weekStart, new_version: newVersion }),
    ),
  matchEmployee: (id: string, employeeId: string) =>
    checked(
      TimesheetReadSchema,
      http.post(`/api/timesheets/${id}/match`, { employee_id: employeeId }),
    ),
  recalculate: (id: string) =>
    checked(TimesheetReadSchema, http.post(`/api/timesheets/${id}/recalculate`)),
  /** Every version, newest first (the first is the timesheet as it is now). */
  listVersions: (id: string) =>
    checked(z.array(TimesheetVersionSummarySchema), http.get(`/api/timesheets/${id}/versions`)),
  getVersion: (id: string, version: number) =>
    checked(TimesheetVersionReadSchema, http.get(`/api/timesheets/${id}/versions/${version}`)),
  /** Go back to a version (its number too, no new version), back in review. */
  restoreVersion: (id: string, version: number, reason?: string) =>
    checked(
      TimesheetReadSchema,
      http.post(`/api/timesheets/${id}/versions/${version}/restore`, { reason: reason || null }),
    ),
  approve: (id: string, notes?: string) =>
    checked(
      TimesheetReadSchema,
      http.post(`/api/timesheets/${id}/approve`, { notes: notes || null }),
    ),
  reject: (id: string, reason: string) =>
    checked(TimesheetReadSchema, http.post(`/api/timesheets/${id}/reject`, { reason })),
  bulkApprove: (ids: string[], notes?: string) =>
    checked(
      BulkResultSchema,
      http.post("/api/timesheets/bulk/approve", {
        timesheet_ids: ids,
        notes: notes || null,
        include_high_severity: false,
      }),
    ),
  bulkReject: (ids: string[], reason: string) =>
    checked(
      BulkResultSchema,
      http.post("/api/timesheets/bulk/reject", { timesheet_ids: ids, reason }),
    ),
};
