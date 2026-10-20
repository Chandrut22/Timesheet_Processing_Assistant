import { describe, expect, it } from "vitest";
import {
  backendWeekday,
  daysBetween,
  formatHours,
  formatMoney,
  formatPercent,
  formatWeek,
  humanize,
  latestWeekStart,
  splitList,
} from "../src/lib/format";

describe("format", () => {
  it("formats money, keeping null as null (rate missing)", () => {
    expect(formatMoney(null, "INR")).toBeNull();
    expect(formatMoney(1234.5, "INR")).toContain("1,234.50");
    expect(formatMoney(10, "bad")).toBe("10.00");
  });

  it("formats hours and percents", () => {
    expect(formatHours(8)).toBe("8");
    expect(formatHours(7.25)).toBe("7.25");
    expect(formatHours(null)).toBe("—");
    expect(formatPercent(0.873)).toBe("87%");
  });

  it("labels a week", () => {
    expect(formatWeek("2026-10-12")).toBe("12–18 Oct 2026");
    expect(formatWeek("2026-09-28")).toBe("28 Sep – 4 Oct 2026");
    expect(formatWeek(null)).toBe("—");
  });

  it("uses the backend weekday numbering (0 = Monday)", () => {
    expect(backendWeekday("2026-10-12")).toBe(0); // Monday
    expect(backendWeekday("2026-10-18")).toBe(6); // Sunday
  });

  it("finds the latest week start on or before a date", () => {
    const sunday = new Date(2026, 9, 18);
    expect(latestWeekStart(0, sunday)).toBe("2026-10-12");
    expect(latestWeekStart(6, sunday)).toBe("2026-10-18");
  });

  it("counts days and splits lists", () => {
    expect(daysBetween("2026-10-12", "2026-10-18")).toBe(6);
    expect(splitList(" a, b ,,c\nd ")).toEqual(["a", "b", "c", "d"]);
    expect(humanize("needs_review")).toBe("Needs review");
  });
});
