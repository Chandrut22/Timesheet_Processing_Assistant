// Typed functions for every core-service endpoint (through the /api proxy).
import { cleanParams, filenameFromDisposition, http, saveBlob } from "./client";
import type {
  AuditEventRead,
  BulkResult,
  CompanyCreate,
  CompanyRead,
  CompanyUpdate,
  EmployeeCreate,
  EmployeeRead,
  EmployeeUpdate,
  EntryInput,
  ExportBatchRead,
  ExportPreview,
  HolidayCreate,
  HolidayRead,
  Page,
  PrincipalRead,
  ReprocessRunRead,
  SeverityFilter,
  SortOrder,
  SubmissionRead,
  SubmissionSource,
  SubmissionState,
  SubmissionStatus,
  SubmissionTimeline,
  TimesheetRead,
  TimesheetSort,
  TimesheetStatus,
  WhitelistRead,
} from "./models";

const data = <T>(p: Promise<{ data: T }>): Promise<T> => p.then((r) => r.data);

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
  me: () => data(http.get<PrincipalRead>("/api/me")),

  // Timesheets
  listTimesheets: (params: TimesheetListParams) =>
    data(http.get<Page<TimesheetRead>>("/api/timesheets", { params: cleanParams(params) })),
  getTimesheet: (id: string) => data(http.get<TimesheetRead>(`/api/timesheets/${id}`)),
  updateEntries: (id: string, entries: EntryInput[]) =>
    data(http.patch<TimesheetRead>(`/api/timesheets/${id}/entries`, { entries })),
  matchEmployee: (id: string, employeeId: string) =>
    data(http.post<TimesheetRead>(`/api/timesheets/${id}/match`, { employee_id: employeeId })),
  recalculate: (id: string) => data(http.post<TimesheetRead>(`/api/timesheets/${id}/recalculate`)),
  approve: (id: string, notes?: string) =>
    data(http.post<TimesheetRead>(`/api/timesheets/${id}/approve`, { notes: notes || null })),
  reject: (id: string, reason: string) =>
    data(http.post<TimesheetRead>(`/api/timesheets/${id}/reject`, { reason })),
  bulkApprove: (ids: string[], notes?: string) =>
    data(
      http.post<BulkResult>("/api/timesheets/bulk/approve", {
        timesheet_ids: ids,
        notes: notes || null,
        include_high_severity: false,
      }),
    ),
  bulkReject: (ids: string[], reason: string) =>
    data(http.post<BulkResult>("/api/timesheets/bulk/reject", { timesheet_ids: ids, reason })),

  // Submissions and uploads
  listSubmissions: (params: SubmissionListParams) =>
    data(http.get<Page<SubmissionRead>>("/api/submissions", { params: cleanParams(params) })),
  getSubmission: (id: string) => data(http.get<SubmissionRead>(`/api/submissions/${id}`)),
  getTimeline: (id: string) =>
    data(http.get<SubmissionTimeline>(`/api/submissions/${id}/timeline`)),
  /** confirmApproved: send after a 409 `confirmation_required` to replace approved timesheets. */
  reprocess: (id: string, reason: string, documentId?: string | null, confirmApproved = false) =>
    data(
      http.post<ReprocessRunRead>(`/api/submissions/${id}/reprocess`, {
        reason,
        document_id: documentId || null,
        confirm_approved: confirmApproved,
      }),
    ),
  reprocessRuns: (id: string) =>
    data(http.get<ReprocessRunRead[]>(`/api/submissions/${id}/reprocess-runs`)),
  upload: (files: File[], companyId?: string, onProgress?: (pct: number) => void) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    if (companyId) form.append("company_id", companyId);
    return data(
      http.post<SubmissionRead>("/api/uploads", form, {
        onUploadProgress: (e) => {
          if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100));
        },
      }),
    );
  },

  // Audit
  listAuditEvents: (entityType: "timesheet" | "submission", entityId: string) =>
    data(
      http.get<AuditEventRead[]>("/api/audit-events", {
        params: { entity_type: entityType, entity_id: entityId },
      }),
    ),

  // Companies
  listCompanies: (params: CompanyListParams) =>
    data(http.get<Page<CompanyRead>>("/api/companies", { params: cleanParams(params) })),
  getCompany: (id: string) => data(http.get<CompanyRead>(`/api/companies/${id}`)),
  createCompany: (body: CompanyCreate) => data(http.post<CompanyRead>("/api/companies", body)),
  updateCompany: (id: string, body: CompanyUpdate) =>
    data(http.patch<CompanyRead>(`/api/companies/${id}`, body)),
  listWhitelist: (companyId: string) =>
    data(http.get<WhitelistRead[]>(`/api/companies/${companyId}/whitelist`)),
  addWhitelist: (companyId: string, value: string) =>
    data(http.post<WhitelistRead>(`/api/companies/${companyId}/whitelist`, { value })),
  removeWhitelist: (companyId: string, entryId: string) =>
    http.delete(`/api/companies/${companyId}/whitelist/${entryId}`).then(() => undefined),

  // Employees
  listEmployees: (params: EmployeeListParams) =>
    data(http.get<Page<EmployeeRead>>("/api/employees", { params: cleanParams(params) })),
  getEmployee: (id: string) => data(http.get<EmployeeRead>(`/api/employees/${id}`)),
  createEmployee: (body: EmployeeCreate) => data(http.post<EmployeeRead>("/api/employees", body)),
  updateEmployee: (id: string, body: EmployeeUpdate) =>
    data(http.patch<EmployeeRead>(`/api/employees/${id}`, body)),

  // Holidays
  listHolidays: (params: HolidayListParams) =>
    data(http.get<HolidayRead[]>("/api/holidays", { params: cleanParams(params) })),
  createHoliday: (body: HolidayCreate) => data(http.post<HolidayRead>("/api/holidays", body)),
  deleteHoliday: (id: string) => http.delete(`/api/holidays/${id}`).then(() => undefined),

  // Payroll export (admin)
  previewExport: (companyId: string, weekStart: string) =>
    data(
      http.get<ExportPreview>("/api/exports/preview", {
        params: { company_id: companyId, week_start: weekStart },
      }),
    ),
  createExport: (companyId: string, weekStart: string, allowPending: boolean) =>
    data(
      http.post<ExportBatchRead>("/api/exports", {
        company_id: companyId,
        week_start: weekStart,
        allow_pending: allowPending,
      }),
    ),
  listExports: (params: ExportListParams) =>
    data(http.get<Page<ExportBatchRead>>("/api/exports", { params: cleanParams(params) })),
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
