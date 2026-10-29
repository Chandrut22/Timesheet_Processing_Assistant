import { describe, expect, it } from "vitest";
import { BulkDeleteResultSchema, BulkStatusResultSchema } from "@/services/schemas";
import {
  type BulkRow,
  failedIds,
  headerState,
  resultSummary,
  toggleAllRows,
  toggleRow,
  visibleSelection,
  wouldChange,
} from "./rowSelection";

const ids = ["a", "b", "c", "d", "e"];
const rows: BulkRow[] = [
  { id: "a", label: "A", isActive: true },
  { id: "b", label: "B", isActive: false },
  { id: "c", label: "C", isActive: true, disabled: true },
];
const id = (n: number): string => `00000000-0000-4000-8000-00000000000${n}`;
const noun = { one: "employee", many: "employees" };

describe("toggleRow", () => {
  it("ticks and unticks one row", () => {
    const on = toggleRow(new Set(), "b", ids, null, false);
    expect([...on]).toEqual(["b"]);
    expect([...toggleRow(on, "b", ids, "b", false)]).toEqual([]);
  });

  it("shift-click ticks the whole range since the last click, either direction", () => {
    expect([...toggleRow(new Set(["b"]), "d", ids, "b", true)].sort()).toEqual(["b", "c", "d"]);
    expect([...toggleRow(new Set(["d"]), "b", ids, "d", true)].sort()).toEqual(["b", "c", "d"]);
  });

  it("shift-click on a ticked row unticks the range", () => {
    const all = new Set(ids);
    expect([...toggleRow(all, "d", ids, "b", true)].sort()).toEqual(["a", "e"]);
  });

  it("shift without an earlier click is a plain click", () => {
    expect([...toggleRow(new Set(), "c", ids, null, true)]).toEqual(["c"]);
    expect([...toggleRow(new Set(), "c", ids, "gone", true)]).toEqual(["c"]);
  });
});

describe("select all on this page", () => {
  it("ticks every selectable row, then clears", () => {
    const all = toggleAllRows(new Set(["a"]), ids);
    expect(all.size).toBe(5);
    expect(toggleAllRows(all, ids).size).toBe(0);
  });

  it("reports none / some / all", () => {
    expect(headerState(new Set(), ids)).toBe("none");
    expect(headerState(new Set(["a"]), ids)).toBe("some");
    expect(headerState(new Set(ids), ids)).toBe("all");
    expect(headerState(new Set(), [])).toBe("none");
  });
});

describe("visibleSelection / wouldChange", () => {
  it("keeps only rows on the page that can be selected", () => {
    const shown = visibleSelection(new Set(["a", "c", "zz"]), rows);
    expect(shown.map((r) => r.id)).toEqual(["a"]);
  });

  it("counts only rows whose status would change", () => {
    expect(wouldChange(rows.slice(0, 2), "activate")).toBe(1);
    expect(wouldChange(rows.slice(0, 2), "deactivate")).toBe(1);
    expect(wouldChange([rows[0]], "activate")).toBe(0);
    expect(wouldChange(rows.slice(0, 2), "delete")).toBe(2);
  });
});

describe("results", () => {
  const status = BulkStatusResultSchema.parse({
    requested: 4,
    succeeded: 3,
    failed: 1,
    employees_deactivated: 7,
    results: [
      { id: id(1), ok: true, changed: true, is_active: false, error: null },
      { id: id(2), ok: true, changed: true, is_active: false, error: null },
      { id: id(3), ok: true, changed: false, is_active: false, error: null },
      { id: id(4), ok: false, changed: false, is_active: null, error: "Company not found." },
    ],
  });

  it("the users response (no employees_deactivated) is valid too", () => {
    const users = BulkStatusResultSchema.safeParse({
      requested: 1,
      succeeded: 0,
      failed: 1,
      results: [
        {
          id: id(1),
          ok: false,
          changed: false,
          is_active: true,
          error: "You cannot deactivate your own account.",
        },
      ],
    });
    expect(users.success).toBe(true);
  });

  it("keeps the failed ones selected", () => {
    expect([...failedIds(status)]).toEqual([id(4)]);
  });

  it("summarises changed, unchanged, cascaded and failed", () => {
    expect(resultSummary(status, "deactivate", { one: "company", many: "companies" })).toBe(
      "2 companies deactivated, 1 already inactive, 7 employees deactivated with them, 1 not changed.",
    );
  });

  it("summarises a clean activate", () => {
    const one = BulkStatusResultSchema.parse({
      requested: 1,
      succeeded: 1,
      failed: 0,
      results: [{ id: id(1), ok: true, changed: true, is_active: true, error: null }],
    });
    expect(resultSummary(one, "activate", noun)).toBe("1 employee activated.");
  });

  it("summarises a delete", () => {
    const deleted = BulkDeleteResultSchema.parse({
      requested: 2,
      deleted: 2,
      failed: 0,
      results: [
        { id: id(1), ok: true, changed: true, is_active: null, error: null },
        { id: id(2), ok: true, changed: true, is_active: null, error: null },
      ],
    });
    expect(resultSummary(deleted, "delete", { one: "holiday", many: "holidays" })).toBe(
      "2 holidays deleted.",
    );
  });
});
