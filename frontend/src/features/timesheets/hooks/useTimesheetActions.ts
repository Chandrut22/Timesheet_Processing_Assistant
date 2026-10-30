// Every change to one timesheet. Each goes through useTimesheetMutation: the returned
// timesheet replaces the cached one, the lists, history and versions are refreshed,
// and the screen's success toast is shown.
import type { DefaultError, UseMutationResult } from "@tanstack/react-query";

import { timesheetService } from "../services/timesheetService";
import type { EntryInput, TimesheetRead } from "../types/timesheet";
import { type TimesheetMutationOptions, useTimesheetMutation } from "./useTimesheetMutation";

type Result<V> = UseMutationResult<TimesheetRead, DefaultError, V>;

/** Notes are optional: blank sends none. */
export function useApproveTimesheet(
  timesheetId: string,
  opts: TimesheetMutationOptions<string> = {},
): Result<string> {
  return useTimesheetMutation(
    (notes: string) => timesheetService.approve(timesheetId, notes.trim() || undefined),
    opts,
  );
}

export function useRejectTimesheet(
  timesheetId: string,
  opts: TimesheetMutationOptions<string> = {},
): Result<string> {
  return useTimesheetMutation(
    (reason: string) => timesheetService.reject(timesheetId, reason.trim()),
    opts,
  );
}

export type SaveEntriesVariables = { entries: EntryInput[]; newVersion: boolean };

/** Save the days; newVersion keeps the old data as a version in the history. */
export function useSaveEntries(
  timesheetId: string,
  opts: TimesheetMutationOptions<SaveEntriesVariables> = {},
): Result<SaveEntriesVariables> {
  return useTimesheetMutation(
    ({ entries, newVersion }: SaveEntriesVariables) =>
      timesheetService.updateEntries(timesheetId, entries, newVersion),
    opts,
  );
}

export type SetWeekVariables = { weekStart: string; newVersion: boolean };

export function useSetWeek(
  timesheetId: string,
  opts: TimesheetMutationOptions<SetWeekVariables> = {},
): Result<SetWeekVariables> {
  return useTimesheetMutation(
    ({ weekStart, newVersion }: SetWeekVariables) =>
      timesheetService.setWeek(timesheetId, weekStart, newVersion),
    opts,
  );
}

/** Pick the employee by hand (pay is recalculated). */
export function useMatchEmployee(
  timesheetId: string,
  opts: TimesheetMutationOptions<string> = {},
): Result<string> {
  return useTimesheetMutation(
    (employeeId: string) => timesheetService.matchEmployee(timesheetId, employeeId),
    opts,
  );
}

/** Again with the company's current rules and rates. */
export function useRecalculateTimesheet(
  timesheetId: string,
  opts: TimesheetMutationOptions<void> = {},
): Result<void> {
  return useTimesheetMutation(() => timesheetService.recalculate(timesheetId), opts);
}

/** Go back to a saved version; the reason is optional. */
export function useRestoreVersion(
  timesheetId: string,
  version: number,
  opts: TimesheetMutationOptions<string> = {},
): Result<string> {
  return useTimesheetMutation(
    (reason: string) => timesheetService.restoreVersion(timesheetId, version, reason.trim()),
    opts,
  );
}
