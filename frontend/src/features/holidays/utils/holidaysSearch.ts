export type HolidaysSearch = { year?: number; company_id?: string; active?: "active" | "inactive" };

/** The holidays list's year, company and active filter in the URL. */
export const validateHolidaysSearch = (s: Record<string, unknown>): HolidaysSearch => {
  const y = Number(s.year);
  return {
    year: Number.isInteger(y) && y >= 2000 && y <= 2100 ? y : undefined,
    company_id: typeof s.company_id === "string" && s.company_id ? s.company_id : undefined,
    active: s.active === "active" || s.active === "inactive" ? s.active : undefined,
  };
};
