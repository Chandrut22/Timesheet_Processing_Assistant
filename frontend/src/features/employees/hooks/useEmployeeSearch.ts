import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { employeeKeys } from "../queries/employeeQueries";
import { employeeService } from "../services/employeeService";

type EmployeeListParams = Parameters<typeof employeeService.listEmployees>[0];
type EmployeeListData = Awaited<ReturnType<typeof employeeService.listEmployees>>;

/** A search while a picker is open (no placeholder: an old result list never shows for
 * a new search). Shares the cache with the employees list. */
export function useEmployeeSearch(
  params: EmployeeListParams,
  enabled: boolean,
): UseQueryResult<EmployeeListData> {
  return useQuery({
    queryKey: employeeKeys.list(params),
    queryFn: ({ signal }) => employeeService.listEmployees(params, signal),
    enabled,
  });
}
