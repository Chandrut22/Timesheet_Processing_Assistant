import { cleanParams, http } from "@/lib/axios";
import { BulkStatusResultSchema } from "@/services/schemas";
import {
  EmployeePageSchema,
  EmployeeReadSchema,
  type EmployeeCreate,
  type EmployeeUpdate,
  type EmployeeListParams,
} from "../types/employee";
import { checked } from "@/services/response";

export const employeeService = {
  /** `signal` lets TanStack Query cancel a search that a newer one replaced. */
  listEmployees: (params: EmployeeListParams, signal?: AbortSignal) =>
    checked(
      EmployeePageSchema,
      http.get("/api/employees", { params: cleanParams(params), signal }),
    ),
  getEmployee: (id: string) => checked(EmployeeReadSchema, http.get(`/api/employees/${id}`)),
  createEmployee: (body: EmployeeCreate) =>
    checked(EmployeeReadSchema, http.post("/api/employees", body)),
  updateEmployee: (id: string, body: EmployeeUpdate) =>
    checked(EmployeeReadSchema, http.patch(`/api/employees/${id}`, body)),
  /** Admin: activate / deactivate up to 100 employees; each one is reported on its own. */
  bulkEmployeeStatus: (ids: string[], isActive: boolean) =>
    checked(
      BulkStatusResultSchema,
      http.post("/api/employees/bulk/status", { ids, is_active: isActive }),
    ),
};
