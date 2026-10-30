import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { timesheetKeys } from "../queries/timesheetQueries";
import { timesheetService } from "../services/timesheetService";
import type {
  TimesheetRead,
  TimesheetVersionRead,
  TimesheetVersionSummary,
} from "../types/timesheet";

export function useTimesheet(timesheetId: string): UseQueryResult<TimesheetRead> {
  return useQuery({
    queryKey: timesheetKeys.detail(timesheetId),
    queryFn: () => timesheetService.getTimesheet(timesheetId),
  });
}

export function useTimesheetVersions(
  timesheetId: string,
): UseQueryResult<TimesheetVersionSummary[]> {
  return useQuery({
    queryKey: timesheetKeys.versions(timesheetId),
    queryFn: () => timesheetService.listVersions(timesheetId),
  });
}

/** One saved version's days. Refetched when the timesheet changes (its key is under the
 * versions list's key). */
export function useTimesheetVersion(
  timesheetId: string,
  version: number,
): UseQueryResult<TimesheetVersionRead> {
  return useQuery({
    queryKey: timesheetKeys.version(timesheetId, version),
    queryFn: () => timesheetService.getVersion(timesheetId, version),
    staleTime: Infinity,
  });
}
