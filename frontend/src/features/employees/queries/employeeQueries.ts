import type { EmployeeListParams } from "../types/employee";

/** Query keys for employees. */
export const employeeKeys = {
  all: ["employees"] as const,
  list: (p: EmployeeListParams) => ["employees", "list", p] as const,
  byCompany: (companyId: string) => ["employees", "by-company", companyId] as const,
  detail: (id: string) => ["employees", "detail", id] as const,
};
