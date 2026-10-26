// Version history responses (GET /timesheets/{id}/versions[/{n}]) and the fields the
// timesheet lost (entry ids, superseded_by_id, the "superseded" status).
import fixtures from "@/test/fixtures/api-responses.json";
import { describe, expect, it } from "vitest";
import {
  TimesheetReadSchema,
  TimesheetStatusSchema,
  TimesheetVersionReadSchema,
  TimesheetVersionSummarySchema,
} from "./timesheet";
import { reviewParams } from "@/features/review/utils/search";
import { z } from "zod";

describe("version history schemas", () => {
  it("parse the version list and one version", () => {
    const list = z.array(TimesheetVersionSummarySchema).parse(fixtures.core.timesheetVersions);
    expect(list.map((v) => [v.version, v.current, v.change])).toEqual([
      [2, true, null],
      [1, false, "entries_edited"],
    ]);
    const one = TimesheetVersionReadSchema.parse(fixtures.core.timesheetVersion);
    expect(one.entries.map((e) => e.hours)).toEqual([8, 10.5]);
  });

  it("refuse an unknown change", () => {
    const bad = { ...fixtures.core.timesheetVersions[1], change: "deleted" };
    expect(TimesheetVersionSummarySchema.safeParse(bad).success).toBe(false);
  });
});

describe("timesheets without superseded versions", () => {
  it("days have no id and there is no superseded_by_id", () => {
    const t = TimesheetReadSchema.parse(fixtures.core.timesheet);
    expect(t.entries.length).toBeGreaterThan(0);
    expect("id" in t.entries[0]).toBe(false);
    expect("superseded_by_id" in t).toBe(false);
  });

  it("superseded is no longer a status, and the review list never asks for it", () => {
    expect(TimesheetStatusSchema.safeParse("superseded").success).toBe(false);
    expect("include_superseded" in reviewParams({})).toBe(false);
  });
});
