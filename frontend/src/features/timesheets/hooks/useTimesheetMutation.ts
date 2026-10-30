import {
  useMutation,
  useQueryClient,
  type UseMutationResult,
  type DefaultError,
} from "@tanstack/react-query";
import { toast } from "sonner";
import type { TimesheetRead } from "../types/timesheet";
import { auditKeys } from "@/features/audit";
import { submissionKeys } from "@/features/submissions";
import { timesheetKeys } from "../queries/timesheetQueries";

/**
 * Shared wiring for every timesheet action: put the returned timesheet in the
 * cache, refresh lists / history, and show a success toast.
 */
export type TimesheetMutationOptions<V> = {
  /** The toast; a function when it depends on what was sent. */
  success?: string | ((t: TimesheetRead, vars: V) => string);
  silentError?: boolean;
  onSuccess?: (t: TimesheetRead) => void;
};

export function useTimesheetMutation<V>(
  fn: (vars: V) => Promise<TimesheetRead>,
  opts: TimesheetMutationOptions<V> = {},
): UseMutationResult<TimesheetRead, DefaultError, V> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    meta: { silentError: opts.silentError },
    // Here, not in mutate(): an editor keyed by its data remounts after a save, and
    // mutate()'s own callbacks don't run for an unmounted component.
    onSuccess: (t, vars) => {
      queryClient.setQueryData(timesheetKeys.detail(t.id), t);
      void queryClient.invalidateQueries({ queryKey: ["timesheets", "list"] });
      void queryClient.invalidateQueries({ queryKey: auditKeys.entity("timesheet", t.id) });
      void queryClient.invalidateQueries({ queryKey: timesheetKeys.versions(t.id) });
      void queryClient.invalidateQueries({ queryKey: submissionKeys.all });
      const message = typeof opts.success === "function" ? opts.success(t, vars) : opts.success;
      if (message) toast.success(message);
      opts.onSuccess?.(t);
    },
  });
}
