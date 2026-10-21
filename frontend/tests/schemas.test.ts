// The hand-written schemas (src/api/schemas) against real responses captured from both
// services (tests/fixtures/api-responses.json), plus the dev-time check itself.
import { describe, expect, it } from "vitest";
import type { z } from "zod";
import fixtures from "./fixtures/api-responses.json";
import { MessageResponseSchema, UserPageSchema } from "../src/api/schemas/auth";
import {
  ImportReportSchema,
  ResponseShapeError,
  checkResponse,
  responseOf,
} from "../src/api/schemas/common";
import {
  CompanyPageSchema,
  EmployeePageSchema,
  ExportBatchPageSchema,
  ExportBatchReadSchema,
  ExportPreviewSchema,
  FlagReadSchema,
  HolidayReadSchema,
  PrincipalReadSchema,
  SubmissionPageSchema,
  SubmissionTimelineSchema,
  TimesheetPageSchema,
  TimesheetReadSchema,
  WhitelistReadSchema,
} from "../src/api/schemas/core";
import { z as zod } from "zod";

const core = fixtures.core;
const auth = fixtures.auth;

const cases: [string, z.ZodType, unknown][] = [
  ["GET /api/me", PrincipalReadSchema, core.me],
  ["GET /api/timesheets", TimesheetPageSchema, core.timesheetPage],
  ["GET /api/timesheets/{id}", TimesheetReadSchema, core.timesheet],
  ["GET /api/submissions", SubmissionPageSchema, core.submissionPage],
  ["GET /api/submissions/{id}/timeline", SubmissionTimelineSchema, core.timeline],
  ["GET /api/companies", CompanyPageSchema, core.companyPage],
  ["GET /api/employees", EmployeePageSchema, core.employeePage],
  ["GET /api/holidays", zod.array(HolidayReadSchema), core.holidays],
  ["GET /api/companies/{id}/whitelist", zod.array(WhitelistReadSchema), core.whitelist],
  ["GET /api/exports/preview", ExportPreviewSchema, core.exportPreview],
  ["POST /api/exports", ExportBatchReadSchema, core.exportBatch],
  ["GET /api/exports", ExportBatchPageSchema, core.exportPage],
  ["POST /api/holidays/import", ImportReportSchema, core.importReport],
  ["GET /users", UserPageSchema, auth.userPage],
  ["POST /users/import", ImportReportSchema, auth.importReport],
  ["POST /auth/forgot-password", MessageResponseSchema, auth.message],
];

describe("schemas match real API responses", () => {
  for (const [what, schema, body] of cases) {
    it(what, () => {
      const result = schema.safeParse(body);
      expect(result.success ? "ok" : zod.prettifyError(result.error)).toBe("ok");
    });
  }

  it("the captured lists are not empty (so the item schemas are really exercised)", () => {
    expect(core.timesheetPage.items.length > 0).toBe(true);
    expect(core.holidays.length > 0).toBe(true);
    expect(auth.userPage.items.length > 0).toBe(true);
    expect(core.importReport.rows.length > 0).toBe(true);
  });
});

describe("checkResponse", () => {
  it("returns the very same object (dev and production behave alike)", () => {
    expect(checkResponse(TimesheetReadSchema, core.timesheet, "x")).toBe(core.timesheet);
  });

  it("throws a ResponseShapeError naming the endpoint and the field when the backend drifts", () => {
    const drifted = { ...core.timesheet, total_hours: "40.00" }; // a string, not a number
    let error: unknown;
    const logged: unknown[] = [];
    const consoleError = console.error;
    console.error = (...args: unknown[]) => void logged.push(args); // expected here: keep the run quiet
    try {
      responseOf(TimesheetReadSchema)({
        data: drifted,
        config: { method: "get", url: "/api/timesheets/1" },
      });
    } catch (e) {
      error = e;
    } finally {
      console.error = consoleError;
    }
    expect(logged.length).toBe(1); // a developer sees it in the browser console too
    expect(error instanceof ResponseShapeError).toBe(true);
    const message = (error as Error).message;
    expect(message.includes("GET /api/timesheets/1")).toBe(true);
    expect(message.includes("total_hours")).toBe(true);
  });

  it("notices a field the frontend relies on that disappeared", () => {
    const missing = Object.fromEntries(
      Object.entries(core.timesheet).filter(([key]) => key !== "week_start"),
    );
    expect(TimesheetReadSchema.safeParse(missing).success).toBe(false);
  });

  it("keeps the extra keys a flag may carry", () => {
    const flag = {
      code: "missing_rows",
      message: "2 people missing",
      severity: "high",
      missing: 2,
    };
    expect(FlagReadSchema.parse(flag)).toEqual(flag);
  });
});
