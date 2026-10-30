import { useMutation, type UseMutationResult } from "@tanstack/react-query";
import { timesheetService, type BulkResult } from "@/features/timesheets";

export function useBulkApprove(
  ids: string[],
  onDone: (result: BulkResult) => void,
): UseMutationResult<BulkResult, Error, string> {
  return useMutation<BulkResult, Error, string>({
    mutationFn: (notes: string) => timesheetService.bulkApprove(ids, notes.trim() || undefined),
    onSuccess: (result) => {
      onDone(result);
    },
  });
}
