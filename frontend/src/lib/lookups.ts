// TimesheetRead carries only company_id / employee_id, so names are looked up
// here (cached). If the backend later adds employee_name / company_name to
// TimesheetRead, `timesheetEmployeeName` uses them automatically.
import { useQueries, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { coreApi } from "@/api/core";
import type { CompanyRead, EmployeeRead, TimesheetRead } from "@/api/models";
import { qk } from "@/api/queryKeys";

const LOOKUP_STALE = 5 * 60_000;

/** All companies (first 100, active and inactive), for selects and name lookups. */
export function useCompanies() {
  return useQuery({
    queryKey: qk.companies.lookup,
    queryFn: () => coreApi.listCompanies({ size: 100, page: 1 }),
    staleTime: LOOKUP_STALE,
    select: (page) => page.items,
  });
}

export function useCompanyMap(): Map<string, CompanyRead> {
  const { data } = useCompanies();
  return useMemo(() => new Map((data ?? []).map((c) => [c.id, c])), [data]);
}

function combineEmployees(results: { data?: { items: EmployeeRead[] } }[]): Map<string, EmployeeRead> {
  const map = new Map<string, EmployeeRead>();
  for (const r of results) for (const e of r.data?.items ?? []) map.set(e.id, e);
  return map;
}

/** Employees for each company id given (first 100 per company), merged into one map. */
export function useEmployeeMap(companyIds: (string | null | undefined)[]): Map<string, EmployeeRead> {
  const ids = useMemo(
    () => [...new Set(companyIds.filter((x): x is string => !!x))].sort(),
    [companyIds],
  );
  return useQueries({
    queries: ids.map((id) => ({
      queryKey: qk.employees.byCompany(id),
      queryFn: () => coreApi.listEmployees({ company_id: id, size: 100, page: 1 }),
      staleTime: LOOKUP_STALE,
    })),
    combine: combineEmployees,
  });
}

type MaybeNamed = { employee_name?: unknown; company_name?: unknown };

export function timesheetEmployeeName(
  t: TimesheetRead,
  employees: Map<string, EmployeeRead>,
): { name: string; matched: boolean; code: string | null } {
  const fromApi = (t as TimesheetRead & MaybeNamed).employee_name;
  if (t.employee_id) {
    const e = employees.get(t.employee_id);
    if (typeof fromApi === "string" && fromApi) return { name: fromApi, matched: true, code: e?.employee_code ?? null };
    if (e) return { name: e.full_name, matched: true, code: e.employee_code };
    return { name: t.extracted_name ?? "Matched employee", matched: true, code: t.extracted_code };
  }
  return { name: t.extracted_name ?? "Unknown", matched: false, code: t.extracted_code };
}

export function timesheetCompanyName(t: TimesheetRead, companies: Map<string, CompanyRead>): string {
  const fromApi = (t as TimesheetRead & MaybeNamed).company_name;
  if (typeof fromApi === "string" && fromApi) return fromApi;
  if (t.company_id) return companies.get(t.company_id)?.name ?? "Unknown company";
  return t.extracted_company_name ? `${t.extracted_company_name} (not matched)` : "—";
}
