import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";
import { useCallback } from "react";

import type { BulkStatusApi } from "@/hooks/useBulkStatusMutation";
import type { MutationCallbacks } from "@/hooks/mutationOptions";

import { holidayKeys } from "../queries/holidayQueries";
import { holidayService } from "../services/holidayService";
import type {
  HolidayBulkCreate,
  HolidayBulkResult,
  HolidayCopy,
  HolidayRead,
} from "../types/holiday";

export const holidayBulkStatus: BulkStatusApi = {
  setStatus: holidayService.bulkHolidayStatus,
  remove: holidayService.bulkDeleteHolidays,
  invalidate: [holidayKeys.all],
};

/** After an import from Excel: show the new holidays. */
export function useRefreshHolidays(): () => void {
  const queryClient = useQueryClient();
  return useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: holidayKeys.all });
  }, [queryClient]);
}

/** One date for every chosen company, in one request (a company that already has a
 * holiday that day is skipped and named in the result). The form shows the error. */
export function useCreateHolidays(
  opts: MutationCallbacks<HolidayBulkResult, HolidayBulkCreate> = {},
): UseMutationResult<HolidayBulkResult, Error, HolidayBulkCreate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: HolidayBulkCreate) => holidayService.bulkCreateHolidays(body),
    meta: { silentError: true },
    onSuccess: (result, body) => {
      void queryClient.invalidateQueries({ queryKey: holidayKeys.all });
      opts.onSuccess?.(result, body);
    },
    onError: (error, variables) => opts.onError?.(error, variables),
  });
}

/** Give other companies the holidays one company already has. The dialog shows the
 * error itself. */
export function useCopyHolidays(
  opts: MutationCallbacks<HolidayBulkResult, HolidayCopy> = {},
): UseMutationResult<HolidayBulkResult, Error, HolidayCopy> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: HolidayCopy) => holidayService.copyHolidays(body),
    meta: { silentError: true },
    onSuccess: (result, body) => {
      void queryClient.invalidateQueries({ queryKey: holidayKeys.all });
      opts.onSuccess?.(result, body);
    },
  });
}

export function useDeleteHoliday(
  opts: MutationCallbacks<void, HolidayRead> = {},
): UseMutationResult<void, Error, HolidayRead> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (h: HolidayRead) => holidayService.deleteHoliday(h.id),
    onSuccess: (_, h) => {
      void queryClient.invalidateQueries({ queryKey: holidayKeys.all });
      opts.onSuccess?.(undefined, h);
    },
  });
}
