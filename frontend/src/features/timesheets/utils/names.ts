import type { CompanyRead } from "@/features/companies";
import type { EmployeeRead } from "@/features/employees";
import type { TimesheetRead } from "../types/timesheet";

type MaybeNamed = { employee_name?: unknown; company_name?: unknown };

export function timesheetEmployeeName(
  t: TimesheetRead,
  employees: Map<string, EmployeeRead>,
): { name: string; matched: boolean; code: string | null } {
  const fromApi = (t as TimesheetRead & MaybeNamed).employee_name;
  if (t.employee_id) {
    const e = employees.get(t.employee_id);
    if (typeof fromApi === "string" && fromApi)
      return { name: fromApi, matched: true, code: e?.employee_code ?? null };
    if (e) return { name: e.full_name, matched: true, code: e.employee_code };
    return { name: t.extracted_name ?? "Matched employee", matched: true, code: t.extracted_code };
  }
  return { name: t.extracted_name ?? "Unknown", matched: false, code: t.extracted_code };
}

export function timesheetCompanyName(
  t: TimesheetRead,
  companies: Map<string, CompanyRead>,
): string {
  const fromApi = (t as TimesheetRead & MaybeNamed).company_name;
  if (typeof fromApi === "string" && fromApi) return fromApi;
  if (t.company_id) return companies.get(t.company_id)?.name ?? "Unknown company";
  return t.extracted_company_name ? `${t.extracted_company_name} (not matched)` : "—";
}
