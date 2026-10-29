import { describe, expect, it } from "vitest";
import { canMatch, isUnmatched, nextUnmatched } from "./match";

const row = (
  id: string,
  employee_id: string | null,
  status = "needs_review",
): { id: string; employee_id: string | null; status: string } => ({
  id,
  employee_id,
  status,
});

describe("match helpers", () => {
  it("knows which rows can still be matched", () => {
    expect(isUnmatched(row("a", null))).toBe(true);
    expect(isUnmatched(row("a", "e1"))).toBe(false);
    expect(isUnmatched(row("a", null, "exported"))).toBe(false);
    expect(canMatch(row("a", "e1", "approved"))).toBe(true);
    expect(canMatch(row("a", "e1", "exported"))).toBe(false);
  });

  it("goes to the next unmatched row below, then wraps to the top", () => {
    const items = [
      row("a", null),
      row("b", "e1"),
      row("c", null),
      row("d", null, "exported"),
      row("e", null),
    ];
    expect(nextUnmatched(items, "a")?.id).toBe("c");
    expect(nextUnmatched(items, "c")?.id).toBe("e");
    expect(nextUnmatched(items, "e")?.id).toBe("a");
  });

  it("is null when the current row was the last unmatched one", () => {
    expect(nextUnmatched([row("a", null), row("b", "e1")], "a")).toBeNull();
    expect(nextUnmatched([], "a")).toBeNull();
  });
});
