// All TanStack Query keys in one place, so invalidation is consistent.
import type {
  CompanyListParams,
  EmployeeListParams,
  ExportListParams,
  HolidayListParams,
  SubmissionListParams,
  TimesheetListParams,
} from "./core";
import type { UserListParams } from "./auth";

export const qk = {
  timesheets: {
    all: ["timesheets"] as const,
    list: (p: TimesheetListParams) => ["timesheets", "list", p] as const,
    detail: (id: string) => ["timesheets", "detail", id] as const,
  },
  submissions: {
    all: ["submissions"] as const,
    list: (p: SubmissionListParams) => ["submissions", "list", p] as const,
    detail: (id: string) => ["submissions", "detail", id] as const,
    timeline: (id: string) => ["submissions", "timeline", id] as const,
    /** The Upload page's "Recent uploads" card (under "submissions", so an upload refreshes it). */
    recentUploads: (p: SubmissionListParams) => ["submissions", "recent-uploads", p] as const,
  },
  audit: (type: "timesheet" | "submission", id: string) => ["audit", type, id] as const,
  companies: {
    all: ["companies"] as const,
    list: (p: CompanyListParams) => ["companies", "list", p] as const,
    lookup: ["companies", "lookup"] as const,
    detail: (id: string) => ["companies", "detail", id] as const,
    whitelist: (id: string) => ["companies", "whitelist", id] as const,
  },
  employees: {
    all: ["employees"] as const,
    list: (p: EmployeeListParams) => ["employees", "list", p] as const,
    byCompany: (companyId: string) => ["employees", "by-company", companyId] as const,
    detail: (id: string) => ["employees", "detail", id] as const,
  },
  holidays: {
    all: ["holidays"] as const,
    list: (p: HolidayListParams) => ["holidays", "list", p] as const,
  },
  exports: {
    all: ["exports"] as const,
    preview: (companyId: string, weekStart: string) =>
      ["exports", "preview", companyId, weekStart] as const,
    list: (p: ExportListParams) => ["exports", "list", p] as const,
  },
  users: {
    all: ["users"] as const,
    list: (p: UserListParams) => ["users", "list", p] as const,
  },
};
