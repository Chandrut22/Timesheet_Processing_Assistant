import { describe, expect, it } from "vitest";
import { describeBulkResult } from "./bulkResult";

const name = (id: string): string => ({ a: "Lakeside", b: "Hillview" })[id] ?? id;

describe("describeBulkResult", () => {
  it("says how many were added and why others were skipped", () => {
    expect(describeBulkResult({ created: 2, skipped: [] }, name)).toBe("Added 2 companies.");
    expect(
      describeBulkResult(
        {
          created: 1,
          skipped: [
            {
              company_id: "b",
              holiday_date: "2026-12-25",
              reason: "Already has 'Noel' on this date.",
            },
          ],
        },
        name,
      ),
    ).toBe("Added 1 company. Skipped 1. Hillview: Already has 'Noel' on this date.");
    expect(
      describeBulkResult({ created: 0, skipped: [] }, name, { one: "holiday", many: "holidays" }),
    ).toBe("Nothing new to add.");
  });
});
