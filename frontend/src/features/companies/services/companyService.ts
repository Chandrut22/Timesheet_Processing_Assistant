import { cleanParams, http } from "@/lib/axios";
import { BulkStatusResultSchema } from "@/services/schemas";
import {
  CompanyPageSchema,
  CompanyReadSchema,
  WhitelistReadSchema,
  type CompanyCreate,
  type CompanyUpdate,
  type CompanyListParams,
} from "../types/company";
import { z } from "zod";
import { checked } from "@/services/response";

export const companyService = {
  /** `signal` lets TanStack Query cancel a search that a newer one replaced. */
  listCompanies: (params: CompanyListParams, signal?: AbortSignal) =>
    checked(CompanyPageSchema, http.get("/api/companies", { params: cleanParams(params), signal })),
  getCompany: (id: string) => checked(CompanyReadSchema, http.get(`/api/companies/${id}`)),
  createCompany: (body: CompanyCreate) =>
    checked(CompanyReadSchema, http.post("/api/companies", body)),
  updateCompany: (id: string, body: CompanyUpdate) =>
    checked(CompanyReadSchema, http.patch(`/api/companies/${id}`, body)),
  /** Admin: activate / deactivate up to 100 companies. Deactivating also deactivates
   * their employees (`employees_deactivated`); activating does not bring them back. */
  bulkCompanyStatus: (ids: string[], isActive: boolean) =>
    checked(
      BulkStatusResultSchema,
      http.post("/api/companies/bulk/status", { ids, is_active: isActive }),
    ),
  listWhitelist: (companyId: string) =>
    checked(z.array(WhitelistReadSchema), http.get(`/api/companies/${companyId}/whitelist`)),
  addWhitelist: (companyId: string, value: string) =>
    checked(WhitelistReadSchema, http.post(`/api/companies/${companyId}/whitelist`, { value })),
  removeWhitelist: (companyId: string, entryId: string) =>
    http.delete(`/api/companies/${companyId}/whitelist/${entryId}`).then(() => undefined),
};
