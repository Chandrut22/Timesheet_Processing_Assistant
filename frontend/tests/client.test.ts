import { describe, expect, it } from "vitest";
import { cleanParams, filenameFromDisposition } from "../src/api/client";

describe("client helpers", () => {
  it("drops empty params", () => {
    expect(cleanParams({ a: "", b: undefined, c: null, d: [], e: "x", f: 0, g: false })).toEqual({
      e: "x",
      f: 0,
      g: false,
    });
  });

  it("reads Content-Disposition file names", () => {
    expect(filenameFromDisposition('attachment; filename="payroll-acme-2026-10-12.csv"')).toBe(
      "payroll-acme-2026-10-12.csv",
    );
    expect(filenameFromDisposition("attachment; filename*=UTF-8''pay%20roll.csv")).toBe(
      "pay roll.csv",
    );
    expect(filenameFromDisposition(undefined)).toBeNull();
  });
});
