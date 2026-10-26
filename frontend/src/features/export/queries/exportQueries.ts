import type { ExportListParams } from "../types/export";

/** Query keys for exports. */
export const exportKeys = {
  all: ["exports"] as const,
  preview: (companyId: string, weekStart: string) =>
    ["exports", "preview", companyId, weekStart] as const,
  list: (p: ExportListParams) => ["exports", "list", p] as const,
};
