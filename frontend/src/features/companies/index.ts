// Public API of the companies feature: other parts of the app import only from here.
// Pages are not exported: only their route files import them (src/routes), so each
// page stays in its own chunk (autoCodeSplitting).
export { CompanySelect } from "./components/CompanySelect";

export { useCompanyMap } from "./hooks/useCompanies";
export { useCompaniesList } from "./hooks/useCompaniesList";
export { useCompanyDetails } from "./hooks/useCompanyDetails";
export { useCompanyWhitelist } from "./hooks/useCompanyWhitelist";

export { CompanyPageSchema, CompanyReadSchema, WhitelistReadSchema } from "./types/company";

export type { CompanyCreate, CompanyListParams, CompanyRead, CompanyUpdate } from "./types/company";
