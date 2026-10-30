import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";

import { employeeKeys } from "../queries/employeeQueries";
import { employeeService } from "../services/employeeService";

type EmployeeListParams = Parameters<typeof employeeService.listEmployees>[0];

type EmployeeListData = Awaited<ReturnType<typeof employeeService.listEmployees>>;

export function useEmployeesList(params: EmployeeListParams): UseQueryResult<EmployeeListData> {
  return useQuery<EmployeeListData>({
    queryKey: employeeKeys.list(params),
    queryFn: ({ signal }) => employeeService.listEmployees(params, signal),
    placeholderData: keepPreviousData,
  });
}
