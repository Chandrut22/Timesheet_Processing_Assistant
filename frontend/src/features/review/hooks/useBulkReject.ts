import { useMutation, type UseMutationResult } from "@tanstack/react-query";
import { timesheetService, type BulkResult } from "@/features/timesheets";

export function useBulkReject(
  ids: string[],
  onDone: (result: BulkResult) => void,
): UseMutationResult<BulkResult, Error, string> {
  return useMutation<BulkResult, Error, string>({
    mutationFn: (reason: string) => timesheetService.bulkReject(ids, reason.trim()),
    onSuccess: (result) => {
      onDone(result);
    },
  });
}
