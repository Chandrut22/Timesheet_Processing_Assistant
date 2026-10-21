// Typed functions for every core-service endpoint (through the /api proxy). Every JSON
// response is checked against its zod schema in dev and tests (schemas/common.ts).
import { cleanParams, filenameFromDisposition, http, saveBlob } from "./client";
import { responseOf } from "./schemas/common";
import {
  AuditEventReadSchema,
  BulkResultSchema,
  CompanyPageSchema,
  CompanyReadSchema,
  EmployeePageSchema,
  EmployeeReadSchema,
  ExportBatchPageSchema,
  ExportBatchReadSchema,
  ExportPreviewSchema,
  HolidayReadSchema,
  PrincipalReadSchema,
  ReprocessRunReadSchema,
  SubmissionPageSchema,
  SubmissionReadSchema,
  SubmissionTimelineSchema,
  TimesheetPageSchema,
  TimesheetReadSchema,
  WhitelistReadSchema,
} from "./schemas/core";
import { z } from "zod";
import type {
  CompanyCreate,
  CompanyUpdate,
  EmployeeCreate,
  EmployeeUpdate,
  EntryInput,
  ExportBatchRead,
  HolidayCreate,
  SeverityFilter,
  SortOrder,
  SubmissionSource,
  SubmissionState,
  SubmissionStatus,
  TimesheetSort,
  TimesheetStatus,
} from "./models";

/** Response checked against `schema` (dev / test) and typed by it. */
const data = <T>(schema: z.ZodType<T>, p: Promise<{ data: unknown }>): Promise<T> =>
  p.then(responseOf(schema));

export type TimesheetListParams = {
  status?: TimesheetStatus[];
  state?: SubmissionState[];
  severity?: SeverityFilter[];
  flag?: string;
  submission_id?: string;
  company_id?: string;
  employee_id?: string;
  matched?: boolean;
  sender?: string;
  q?: string;
  date_from?: string;
  date_to?: string;
  received_from?: string;
  received_to?: string;
  min_confidence?: number;
  max_confidence?: number;
  include_superseded?: boolean;
  sort?: TimesheetSort;
  order?: SortOrder;
  page?: number;
  size?: number;
};

export type SubmissionListParams = {
  status?: SubmissionStatus;
  state?: SubmissionState;
  source?: SubmissionSource;
  company_id?: string;
  page?: number;
  size?: number;
};

export type CompanyListParams = { q?: string; is_active?: boolean; page?: number; size?: number };
export type EmployeeListParams = {
  company_id?: string;
  q?: string;
  is_active?: boolean;
  page?: number;
  size?: number;
};
export type HolidayListParams = { company_id?: string; year?: number };
export type ExportListParams = {
  company_id?: string;
  week_start?: string;
  page?: number;
  size?: number;
};

export const coreApi = {
  me: () => data(PrincipalReadSchema, http.get("/api/me")),

  // Timesheets
  listTimesheets: (params: TimesheetListParams) =>
    data(TimesheetPageSchema, http.get("/api/timesheets", { params: cleanParams(params) })),
  getTimesheet: (id: string) => data(TimesheetReadSchema, http.get(`/api/timesheets/${id}`)),
  updateEntries: (id: string, entries: EntryInput[]) =>
    data(TimesheetReadSchema, http.patch(`/api/timesheets/${id}/entries`, { entries })),
  matchEmployee: (id: string, employeeId: string) =>
    data(
      TimesheetReadSchema,
      http.post(`/api/timesheets/${id}/match`, { employee_id: employeeId }),
    ),
  recalculate: (id: string) =>
    data(TimesheetReadSchema, http.post(`/api/timesheets/${id}/recalculate`)),
  approve: (id: string, notes?: string) =>
    data(TimesheetReadSchema, http.post(`/api/timesheets/${id}/approve`, { notes: notes || null })),
  reject: (id: string, reason: string) =>
    data(TimesheetReadSchema, http.post(`/api/timesheets/${id}/reject`, { reason })),
  bulkApprove: (ids: string[], notes?: string) =>
    data(
      BulkResultSchema,
      http.post("/api/timesheets/bulk/approve", {
        timesheet_ids: ids,
        notes: notes || null,
        include_high_severity: false,
      }),
    ),
  bulkReject: (ids: string[], reason: string) =>
    data(
      BulkResultSchema,
      http.post("/api/timesheets/bulk/reject", { timesheet_ids: ids, reason }),
    ),

  // Submissions and uploads
  listSubmissions: (params: SubmissionListParams) =>
    data(SubmissionPageSchema, http.get("/api/submissions", { params: cleanParams(params) })),
  getSubmission: (id: string) => data(SubmissionReadSchema, http.get(`/api/submissions/${id}`)),
  getTimeline: (id: string) =>
    data(SubmissionTimelineSchema, http.get(`/api/submissions/${id}/timeline`)),
  /** confirmApproved: send after a 409 `confirmation_required` to replace approved timesheets. */
  reprocess: (id: string, reason: string, documentId?: string | null, confirmApproved = false) =>
    data(
      ReprocessRunReadSchema,
      http.post(`/api/submissions/${id}/reprocess`, {
        reason,
        document_id: documentId || null,
        confirm_approved: confirmApproved,
      }),
    ),
  reprocessRuns: (id: string) =>
    data(z.array(ReprocessRunReadSchema), http.get(`/api/submissions/${id}/reprocess-runs`)),
  upload: (files: File[], companyId?: string, onProgress?: (pct: number) => void) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    if (companyId) form.append("company_id", companyId);
    return data(
      SubmissionReadSchema,
      http.post("/api/uploads", form, {
        onUploadProgress: (e) => {
          if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100));
        },
      }),
    );
  },

  // Audit
  listAuditEvents: (entityType: "timesheet" | "submission", entityId: string) =>
    data(
      z.array(AuditEventReadSchema),
      http.get("/api/audit-events", {
        params: { entity_type: entityType, entity_id: entityId },
      }),
    ),

  // Companies
  listCompanies: (params: CompanyListParams) =>
    data(CompanyPageSchema, http.get("/api/companies", { params: cleanParams(params) })),
  getCompany: (id: string) => data(CompanyReadSchema, http.get(`/api/companies/${id}`)),
  createCompany: (body: CompanyCreate) =>
    data(CompanyReadSchema, http.post("/api/companies", body)),
  updateCompany: (id: string, body: CompanyUpdate) =>
    data(CompanyReadSchema, http.patch(`/api/companies/${id}`, body)),
  listWhitelist: (companyId: string) =>
    data(z.array(WhitelistReadSchema), http.get(`/api/companies/${companyId}/whitelist`)),
  addWhitelist: (companyId: string, value: string) =>
    data(WhitelistReadSchema, http.post(`/api/companies/${companyId}/whitelist`, { value })),
  removeWhitelist: (companyId: string, entryId: string) =>
    http.delete(`/api/companies/${companyId}/whitelist/${entryId}`).then(() => undefined),

  // Employees
  listEmployees: (params: EmployeeListParams) =>
    data(EmployeePageSchema, http.get("/api/employees", { params: cleanParams(params) })),
  getEmployee: (id: string) => data(EmployeeReadSchema, http.get(`/api/employees/${id}`)),
  createEmployee: (body: EmployeeCreate) =>
    data(EmployeeReadSchema, http.post("/api/employees", body)),
  updateEmployee: (id: string, body: EmployeeUpdate) =>
    data(EmployeeReadSchema, http.patch(`/api/employees/${id}`, body)),

  // Holidays
  listHolidays: (params: HolidayListParams) =>
    data(z.array(HolidayReadSchema), http.get("/api/holidays", { params: cleanParams(params) })),
  createHoliday: (body: HolidayCreate) => data(HolidayReadSchema, http.post("/api/holidays", body)),
  deleteHoliday: (id: string) => http.delete(`/api/holidays/${id}`).then(() => undefined),

  // Payroll export (admin)
  previewExport: (companyId: string, weekStart: string) =>
    data(
      ExportPreviewSchema,
      http.get("/api/exports/preview", {
        params: { company_id: companyId, week_start: weekStart },
      }),
    ),
  createExport: (companyId: string, weekStart: string, allowPending: boolean) =>
    data(
      ExportBatchReadSchema,
      http.post("/api/exports", {
        company_id: companyId,
        week_start: weekStart,
        allow_pending: allowPending,
      }),
    ),
  listExports: (params: ExportListParams) =>
    data(ExportBatchPageSchema, http.get("/api/exports", { params: cleanParams(params) })),
  downloadExport: async (batch: Pick<ExportBatchRead, "id" | "filename">) => {
    const res = await http.get<Blob>(`/api/exports/${batch.id}/download`, {
      responseType: "blob",
    });
    const name =
      filenameFromDisposition(res.headers["content-disposition"]) ||
      batch.filename ||
      `payroll-${batch.id}.csv`;
    saveBlob(res.data, name);
  },
};
