export type EmployeesSearch = {
  company_id?: string;
  q?: string;
  active?: "all" | "inactive";
  page?: number;
};

/** The employees list's filters and page in the URL. Anything unknown is dropped. */
export const validateEmployeesSearch = (s: Record<string, unknown>): EmployeesSearch => ({
  company_id: typeof s.company_id === "string" && s.company_id ? s.company_id : undefined,
  q: typeof s.q === "string" && s.q ? s.q : undefined,
  active: s.active === "all" || s.active === "inactive" ? s.active : undefined,
  page: Number.isInteger(Number(s.page)) && Number(s.page) > 1 ? Number(s.page) : undefined,
});
