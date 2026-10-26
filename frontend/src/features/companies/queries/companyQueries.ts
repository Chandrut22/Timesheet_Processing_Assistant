import type { CompanyListParams } from "../types/company";

/** Query keys for companies. */
export const companyKeys = {
  all: ["companies"] as const,
  list: (p: CompanyListParams) => ["companies", "list", p] as const,
  lookup: ["companies", "lookup"] as const,
  detail: (id: string) => ["companies", "detail", id] as const,
  whitelist: (id: string) => ["companies", "whitelist", id] as const,
};
