export type ExportSearch = { company_id?: string; week?: string };

/** The export page's company and week (YYYY-MM-DD) in the URL. */
export const validateExportSearch = (s: Record<string, unknown>): ExportSearch => ({
  company_id: typeof s.company_id === "string" && s.company_id ? s.company_id : undefined,
  week: typeof s.week === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s.week) ? s.week : undefined,
});
