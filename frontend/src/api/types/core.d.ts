/**
 * Starter copy of the core-service schemas, written in the same shape that
 * openapi-typescript produces. `npm run gen:api` overwrites this file with the
 * full generated version from http://127.0.0.1:8002/openapi.json.
 */
export type paths = Record<string, never>;
export type webhooks = Record<string, never>;
export interface components {
  schemas: {
    ApproveRequest: { notes?: string | null };
    AuditEventRead: {
      id: string;
      entity_type: string;
      entity_id: string;
      action: string;
      actor_id: string | null;
      actor_name: string | null;
      details: { [key: string]: unknown };
      created_at: string;
    };
    BulkApproveRequest: {
      timesheet_ids: string[];
      notes?: string | null;
      include_high_severity: boolean;
    };
    BulkItemResult: {
      timesheet_id: string;
      ok: boolean;
      status?: string | null;
      error?: string | null;
    };
    BulkRejectRequest: { timesheet_ids: string[]; reason: string };
    BulkResult: {
      requested: number;
      succeeded: number;
      failed: number;
      results: components["schemas"]["BulkItemResult"][];
    };
    CompanyCreate: {
      name: string;
      aliases?: string[];
      hourly_rate: number | string;
      overtime_rate: number | string;
      double_time_rate?: number | string | null;
      holiday_rate: number | string;
      currency: string;
      daily_ot_after: number | string;
      weekly_ot_after: number | string;
      double_time_after?: number | string | null;
      week_start: number;
    };
    CompanyRead: {
      id: string;
      name: string;
      aliases: string[];
      hourly_rate: number;
      overtime_rate: number;
      double_time_rate: number | null;
      holiday_rate: number;
      currency: string;
      daily_ot_after: number;
      weekly_ot_after: number;
      double_time_after: number | null;
      week_start: number;
      is_active: boolean;
      created_at: string;
      updated_at: string;
    };
    CompanyUpdate: {
      name?: string | null;
      aliases?: string[] | null;
      hourly_rate?: number | string | null;
      overtime_rate?: number | string | null;
      double_time_rate?: number | string | null;
      holiday_rate?: number | string | null;
      currency?: string | null;
      daily_ot_after?: number | string | null;
      weekly_ot_after?: number | string | null;
      double_time_after?: number | string | null;
      week_start?: number | null;
      is_active?: boolean | null;
    };
    DocumentRead: {
      id: string;
      filename: string;
      content_type: string;
      size_bytes: number;
      sha256: string;
      status: string;
      error: string | null;
      /** How much of a large file was read (pages / sheets); null when all of it was. */
      read_limit?: { [key: string]: unknown } | string | null;
      created_at: string;
    };
    EmployeeCreate: {
      company_id: string;
      employee_code: string;
      full_name: string;
      email?: string | null;
      aliases?: string[];
      assignment_start?: string | null;
      assignment_end?: string | null;
    };
    EmployeeRead: {
      id: string;
      company_id: string;
      employee_code: string;
      full_name: string;
      email: string | null;
      aliases: string[];
      assignment_start: string | null;
      assignment_end: string | null;
      is_active: boolean;
      created_at: string;
      updated_at: string;
    };
    EmployeeUpdate: {
      employee_code?: string | null;
      full_name?: string | null;
      email?: string | null;
      aliases?: string[] | null;
      assignment_start?: string | null;
      assignment_end?: string | null;
      is_active?: boolean | null;
    };
    EntriesUpdate: { entries: components["schemas"]["EntryInput"][] };
    EntryInput: {
      work_date: string;
      hours: number | string;
      double_time_marked: boolean;
      is_holiday: boolean;
      note?: string | null;
    };
    ExportBatchRead: {
      id: string;
      company_id: string;
      company_name: string;
      week_start: string;
      week_end: string;
      row_count: number;
      regular_hours: number;
      overtime_hours: number;
      double_time_hours: number;
      holiday_hours: number;
      currency: string;
      regular_amount: number;
      overtime_amount: number;
      double_time_amount: number;
      holiday_amount: number;
      gross_amount: number;
      filename: string;
      created_by_name: string | null;
      created_at: string;
    };
    ExportCreate: { company_id: string; week_start: string; allow_pending: boolean };
    ExportPreview: {
      company_id: string;
      company_name: string;
      week_start: string;
      week_end: string;
      currency: string;
      rows: components["schemas"]["ExportRowRead"][];
      totals: components["schemas"]["ExportTotalsRead"];
      pending_review: number;
      rejected: number;
      already_exported: number;
      problems: string[];
    };
    ExportRowRead: {
      timesheet_id: string;
      employee_id: string;
      employee_code: string;
      employee_name: string;
      regular_hours: number;
      overtime_hours: number;
      double_time_hours: number;
      holiday_hours: number;
      total_hours: number;
      currency: string | null;
      hourly_rate: number | null;
      overtime_rate: number | null;
      double_time_rate: number | null;
      holiday_rate: number | null;
      regular_amount: number | null;
      overtime_amount: number | null;
      double_time_amount: number | null;
      holiday_amount: number | null;
      gross_amount: number | null;
      approved_by: string | null;
      approved_at: string | null;
    };
    ExportTotalsRead: {
      rows: number;
      regular_hours: number;
      overtime_hours: number;
      double_time_hours: number;
      holiday_hours: number;
      total_hours: number;
      regular_amount: number;
      overtime_amount: number;
      double_time_amount: number;
      holiday_amount: number;
      gross_amount: number;
      unpriced: number;
    };
    FlagRead: {
      code: string;
      message: string;
      severity: string;
      [key: string]: unknown;
    };
    HTTPValidationError: { detail?: components["schemas"]["ValidationError"][] };
    HolidayCreate: { company_id?: string | null; holiday_date: string; name: string };
    HolidayRead: {
      id: string;
      company_id: string | null;
      holiday_date: string;
      name: string;
      created_at: string;
    };
    MatchRequest: { employee_id: string };
    Page_CompanyRead_: {
      items: components["schemas"]["CompanyRead"][];
      total: number;
      page: number;
      size: number;
    };
    Page_EmployeeRead_: {
      items: components["schemas"]["EmployeeRead"][];
      total: number;
      page: number;
      size: number;
    };
    Page_ExportBatchRead_: {
      items: components["schemas"]["ExportBatchRead"][];
      total: number;
      page: number;
      size: number;
    };
    Page_SubmissionRead_: {
      items: components["schemas"]["SubmissionRead"][];
      total: number;
      page: number;
      size: number;
    };
    Page_TimesheetRead_: {
      items: components["schemas"]["TimesheetRead"][];
      total: number;
      page: number;
      size: number;
    };
    PrincipalRead: {
      id: string;
      role: components["schemas"]["RoleName"];
      name: string;
      email: string;
    };
    ProcessingStepRead: {
      id: string;
      step: string;
      result: string;
      message: string;
      document_id: string | null;
      timesheet_id: string | null;
      input: { [key: string]: unknown };
      output: { [key: string]: unknown };
      error_details: string | null;
      duration_ms: number;
      reprocess_run_id: string | null;
      trace_id?: string | null;
      created_at: string;
    };
    RejectRequest: { reason: string };
    ReprocessRequest: {
      reason: string;
      document_id?: string | null;
      /** Replace timesheets that are already approved (after a 409 confirmation_required). */
      confirm_approved: boolean;
    };
    ReprocessRunRead: {
      id: string;
      submission_id: string;
      document_id: string | null;
      reason: string;
      requested_by_name: string;
      status: string;
      before_result: { [key: string]: unknown };
      after_result: { [key: string]: unknown } | null;
      error: string | null;
      created_at: string;
      completed_at: string | null;
    };
    RoleName: "admin" | "reviewer";
    SeverityFilter: "high" | "medium" | "low" | "none";
    SortOrder: "asc" | "desc";
    StateChangeRead: {
      id: string;
      from_state: string | null;
      to_state: string;
      reason: string | null;
      actor_name: string | null;
      created_at: string;
    };
    SubmissionRead: {
      id: string;
      source: string;
      status: string;
      state: string;
      state_reason: string | null;
      company_id: string | null;
      sender_email: string | null;
      subject: string | null;
      uploaded_by_id: string | null;
      uploaded_by_name: string | null;
      received_at: string;
      processed_at: string | null;
      error: string | null;
      attempts: number;
      retry_at: string | null;
      documents: components["schemas"]["DocumentRead"][];
    };
    SubmissionSource: "email" | "upload";
    SubmissionState:
      | "received"
      | "reading"
      | "matching"
      | "rule_checks"
      | "awaiting_review"
      | "approved"
      | "rejected"
      | "exported"
      | "ignored"
      | "failed"
      | "reprocessing";
    SubmissionStatus: "received" | "processing" | "processed" | "failed" | "ignored";
    SubmissionTimeline: {
      submission: components["schemas"]["SubmissionRead"];
      states: components["schemas"]["StateChangeRead"][];
      steps: components["schemas"]["ProcessingStepRead"][];
      audit: components["schemas"]["AuditEventRead"][];
      reprocess_runs: components["schemas"]["ReprocessRunRead"][];
    };
    TimesheetEntryRead: {
      id: string;
      work_date: string;
      hours: number;
      is_holiday: boolean;
      sheet_holiday: boolean;
      double_time_marked: boolean;
      note: string | null;
    };
    TimesheetRead: {
      id: string;
      submission_id: string;
      document_id: string | null;
      company_id: string | null;
      employee_id: string | null;
      extracted_name: string | null;
      extracted_code: string | null;
      extracted_company_name: string | null;
      week_start: string | null;
      status: string;
      version: number;
      reprocess_run_id: string | null;
      superseded_by_id: string | null;
      regular_hours: number;
      overtime_hours: number;
      double_time_hours: number;
      holiday_hours: number;
      total_hours: number;
      stated_total: number | null;
      email_stated_total: number | null;
      currency: string | null;
      hourly_rate: number | null;
      overtime_rate: number | null;
      double_time_rate: number | null;
      holiday_rate: number | null;
      regular_amount: number | null;
      overtime_amount: number | null;
      double_time_amount: number | null;
      holiday_amount: number | null;
      gross_amount: number | null;
      read_confidence: number | null;
      confidence: number | null;
      match_method: string | null;
      match_reason: string | null;
      flags: components["schemas"]["FlagRead"][];
      severity: string | null;
      notes: string | null;
      reviewed_by_name: string | null;
      reviewed_at: string | null;
      created_at: string;
      entries: components["schemas"]["TimesheetEntryRead"][];
    };
    TimesheetSort: "received" | "week" | "employee" | "hours" | "gross" | "confidence" | "severity";
    TimesheetStatus: "needs_review" | "approved" | "rejected" | "exported" | "superseded";
    ValidationError: {
      loc: (string | number)[];
      msg: string;
      type: string;
      input?: unknown;
      ctx?: Record<string, never>;
    };
    WhitelistCreate: { value: string };
    WhitelistRead: {
      id: string;
      company_id: string;
      kind: string;
      value: string;
      created_at: string;
    };
  };
  responses: never;
  parameters: never;
  requestBodies: never;
  headers: never;
  pathItems: never;
}
export type $defs = Record<string, never>;
export type operations = Record<string, never>;
