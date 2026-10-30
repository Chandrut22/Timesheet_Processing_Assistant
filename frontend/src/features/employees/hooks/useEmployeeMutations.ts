import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";
import { useCallback } from "react";

import type { BulkStatusApi } from "@/hooks/useBulkStatusMutation";
import type { MutationCallbacks } from "@/hooks/mutationOptions";

import { employeeKeys } from "../queries/employeeQueries";
import { employeeService } from "../services/employeeService";
import type { EmployeeCreate, EmployeeRead, EmployeeUpdate } from "../types/employee";

export const employeeBulkStatus: BulkStatusApi = {
  setStatus: employeeService.bulkEmployeeStatus,
  invalidate: [employeeKeys.all],
};

/** After an import from Excel: show the new employees. */
export function useRefreshEmployees(): () => void {
  const queryClient = useQueryClient();
  return useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: employeeKeys.all });
  }, [queryClient]);
}

/** id null = a new employee. */
export type SaveEmployeeVariables =
  | { id: null; body: EmployeeCreate }
  | { id: string; body: EmployeeUpdate };

/** Create or update one employee. The form shows the error itself. */
export function useSaveEmployee(
  opts: MutationCallbacks<EmployeeRead, SaveEmployeeVariables> = {},
): UseMutationResult<EmployeeRead, Error, SaveEmployeeVariables> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (v: SaveEmployeeVariables) =>
      v.id === null
        ? employeeService.createEmployee(v.body)
        : employeeService.updateEmployee(v.id, v.body),
    meta: { silentError: true },
    onSuccess: (e, v) => {
      void queryClient.invalidateQueries({ queryKey: employeeKeys.all });
      opts.onSuccess?.(e, v);
    },
  });
}
