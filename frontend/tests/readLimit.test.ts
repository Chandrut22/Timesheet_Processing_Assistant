import { describe, expect, it } from "vitest";
import { describeReadLimit } from "../src/features/submissions/readLimit";
import { traceUrl } from "../src/lib/tracing";

describe("describeReadLimit", () => {
  it("is empty when the whole file was read", () => {
    expect(describeReadLimit(null)).toBeNull();
    expect(describeReadLimit({})).toBeNull();
    expect(describeReadLimit({ pages_read: 10, total_pages: 10 })).toBeNull();
  });

  it("describes pages, sheets and rows", () => {
    expect(describeReadLimit({ pages_read: 50, total_pages: 100 })).toBe("Read pages 1–50 of 100");
    expect(describeReadLimit({ sheets_skipped: ["Feb", "Mar"] })).toBe(
      "2 sheets not read (Feb, Mar)",
    );
    expect(describeReadLimit({ sheets_read: 3, total_sheets: 5 })).toBe("2 sheets not read");
    expect(describeReadLimit({ rows_read: 500, total_rows: 900 })).toBe("Read 500 of 900 rows");
  });

  it("passes a plain message through", () => {
    expect(describeReadLimit("Only the first 50 pages were read")).toBe(
      "Only the first 50 pages were read",
    );
    expect(describeReadLimit({ message: "Trimmed" })).toBe("Trimmed");
  });
});

describe("traceUrl", () => {
  it("needs both the Jaeger URL and a trace id", () => {
    expect(traceUrl("abc", "http://localhost:16686/")).toBe("http://localhost:16686/trace/abc");
    expect(traceUrl("abc", "")).toBeNull();
    expect(traceUrl(null, "http://localhost:16686")).toBeNull();
  });
});
