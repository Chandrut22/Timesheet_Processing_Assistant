import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { TimesheetRead } from "@/api/models";
import { qk } from "@/api/queryKeys";

/**
 * Shared wiring for every timesheet action: put the returned timesheet in the
 * cache, refresh lists / history, and show a success toast.
 */
export function useTimesheetMutation<V>(
  fn: (vars: V) => Promise<TimesheetRead>,
  opts: { success?: string; silentError?: boolean; onSuccess?: (t: TimesheetRead) => void } = {},
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    meta: { silentError: opts.silentError },
    onSuccess: (t) => {
      queryClient.setQueryData(qk.timesheets.detail(t.id), t);
      void queryClient.invalidateQueries({ queryKey: ["timesheets", "list"] });
      void queryClient.invalidateQueries({ queryKey: qk.audit("timesheet", t.id) });
      void queryClient.invalidateQueries({ queryKey: qk.timesheets.versions(t.id) });
      void queryClient.invalidateQueries({ queryKey: qk.submissions.all });
      if (opts.success) toast.success(opts.success);
      opts.onSuccess?.(t);
    },
  });
}
