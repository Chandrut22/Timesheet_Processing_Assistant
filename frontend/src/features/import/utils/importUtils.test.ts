import { describe, expect, it } from "vitest";
import type { ImportReport } from "../types/import";
import { canCommit, onDuplicateOptions, rowProblems, summarize } from "./importUtils";

const report = (over: Partial<ImportReport> = {}): ImportReport => ({
  resource: "employees",
  file_name: "staff.csv",
  dry_run: true,
  committed: false,
  on_error: "abort",
  on_duplicate: "error",
  total_rows: 3,
  created: 3,
  updated: 0,
  skipped: 0,
  failed: 0,
  warnings: [],
  rows: [],
  rows_omitted: 0,
  ...over,
});

describe("import dialog helpers", () => {
  it("summarizes a check and a committed import", () => {
    expect(summarize(report(), "employees")).toBe("Would create 3 employees.");
    expect(summarize(report({ created: 1, skipped: 2, failed: 1 }), "employees")).toBe(
      "Would create 1 employee, skip 2. 1 row has problems.",
    );
    expect(
      summarize(report({ dry_run: false, committed: true, created: 2, updated: 1 }), "companies"),
    ).toBe("Created 2 companies, updated 1.");
    expect(
      summarize(report({ dry_run: false, committed: false, created: 2, failed: 3 }), "users"),
    ).toBe("Nothing was imported: 3 rows have problems.");
  });

  it("offers Import only after a clean check (or when failed rows are skipped)", () => {
    expect(canCommit(null)).toBe(false);
    expect(canCommit(report())).toBe(true);
    expect(canCommit(report({ failed: 1 }))).toBe(false); // abort: all or nothing
    expect(canCommit(report({ failed: 1, on_error: "skip" }))).toBe(true);
    expect(canCommit(report({ created: 0, skipped: 3 }))).toBe(false); // nothing to write
    expect(canCommit(report({ dry_run: false, committed: true }))).toBe(false);
  });

  it("never offers 'update' for users", () => {
    expect(onDuplicateOptions("users").map((o) => o.value)).toEqual(["error", "skip"]);
    expect(onDuplicateOptions("employees").map((o) => o.value)).toEqual([
      "error",
      "skip",
      "update",
    ]);
  });

  it("names the column of each problem", () => {
    expect(
      rowProblems({
        row: 4,
        status: "failed",
        errors: [
          { column: "email", message: "value is not a valid email address" },
          { column: null, message: "Same email as row 2." },
        ],
        warnings: [],
      }),
    ).toBe("email: value is not a valid email address; Same email as row 2.");
  });
});
