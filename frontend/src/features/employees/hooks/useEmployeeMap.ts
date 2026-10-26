import { useQueries } from "@tanstack/react-query";
import { useMemo } from "react";
import type { EmployeeRead } from "../types/employee";
import { LOOKUP_STALE } from "@/config/constants";
import { employeeService } from "../services/employeeService";
import { employeeKeys } from "../queries/employeeQueries";

function combineEmployees(
  results: { data?: { items: EmployeeRead[] } }[],
): Map<string, EmployeeRead> {
  const map = new Map<string, EmployeeRead>();
  for (const r of results) for (const e of r.data?.items ?? []) map.set(e.id, e);
  return map;
}

/** Employees for each company id given (first 100 per company), merged into one map. */
export function useEmployeeMap(
  companyIds: (string | null | undefined)[],
): Map<string, EmployeeRead> {
  const ids = useMemo(
    () => [...new Set(companyIds.filter((x): x is string => !!x))].sort(),
    [companyIds],
  );
  return useQueries({
    queries: ids.map((id) => ({
      queryKey: employeeKeys.byCompany(id),
      queryFn: () => employeeService.listEmployees({ company_id: id, size: 100, page: 1 }),
      staleTime: LOOKUP_STALE,
    })),
    combine: combineEmployees,
  });
}
