import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { timesheetKeys } from "@/features/timesheets";
import type { MutationCallbacks } from "@/hooks/mutationOptions";

import { submissionKeys } from "../queries/submissionQueries";
import { submissionService } from "../services/submissionService";
import type { ReprocessRunRead } from "../types/submission";

export type ReprocessVariables = {
  reason: string;
  /** One attachment only; null = the whole email. */
  documentId: string | null;
  /** Send after a 409 confirmation_required, to replace approved timesheets. */
  confirmApproved: boolean;
  /** Fetch the email again from the mailbox. */
  refetch: boolean;
};

/** Queue a reprocess. Its timesheets change, so both lists are refreshed. The dialog
 * shows the error itself. */
export function useReprocess(
  submissionId: string,
  opts: MutationCallbacks<ReprocessRunRead, ReprocessVariables> = {},
): UseMutationResult<ReprocessRunRead, Error, ReprocessVariables> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (v: ReprocessVariables) =>
      submissionService.reprocess(
        submissionId,
        v.reason,
        v.documentId,
        v.confirmApproved,
        v.refetch,
      ),
    meta: { silentError: true },
    onSuccess: (run, v) => {
      void queryClient.invalidateQueries({ queryKey: submissionKeys.all });
      void queryClient.invalidateQueries({ queryKey: timesheetKeys.all });
      opts.onSuccess?.(run, v);
    },
    onError: (error, variables) => opts.onError?.(error, variables),
  });
}
