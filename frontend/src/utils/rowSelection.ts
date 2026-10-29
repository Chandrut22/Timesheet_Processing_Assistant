// Row selection for the bulk activate / deactivate / delete bars (employees, companies,
// holidays, users). Pure functions, so the rules are tested without a browser.
import type { BulkDeleteResult, BulkStatusResult } from "@/types/api";

/** One row as the bulk bar sees it. */
export type BulkRow = {
  id: string;
  label: string;
  isActive: boolean;
  /** Rows that cannot be selected (your own user, for example). */
  disabled?: boolean;
  disabledReason?: string;
};

export type BulkAction = "activate" | "deactivate" | "delete";

/**
 * Tick or untick one row. With shift held and an earlier click on this page, every
 * selectable row between the two gets the same state as the clicked one.
 */
export function toggleRow(
  selected: ReadonlySet<string>,
  id: string,
  selectable: readonly string[],
  anchor: string | null,
  shift: boolean,
): Set<string> {
  const next = new Set(selected);
  const on = !selected.has(id);
  const from = anchor === null ? -1 : selectable.indexOf(anchor);
  const to = selectable.indexOf(id);
  if (shift && from >= 0 && to >= 0) {
    const [lo, hi] = from < to ? [from, to] : [to, from];
    for (const rowId of selectable.slice(lo, hi + 1)) {
      if (on) next.add(rowId);
      else next.delete(rowId);
    }
    return next;
  }
  if (on) next.add(id);
  else next.delete(id);
  return next;
}

/** The header box: everything on the page, or nothing when everything is already ticked. */
export function toggleAllRows(
  selected: ReadonlySet<string>,
  selectable: readonly string[],
): Set<string> {
  return headerState(selected, selectable) === "all" ? new Set() : new Set(selectable);
}

export function headerState(
  selected: ReadonlySet<string>,
  selectable: readonly string[],
): "all" | "some" | "none" {
  const ticked = selectable.filter((id) => selected.has(id)).length;
  if (ticked === 0) return "none";
  return ticked === selectable.length ? "all" : "some";
}

/** Only rows still on the page and selectable count (the list may have changed). */
export function visibleSelection(
  selected: ReadonlySet<string>,
  rows: readonly BulkRow[],
): BulkRow[] {
  return rows.filter((r) => !r.disabled && selected.has(r.id));
}

/** How many of the selected rows the action would actually change. */
export function wouldChange(rows: readonly BulkRow[], action: BulkAction): number {
  if (action === "delete") return rows.length;
  const target = action === "activate";
  return rows.filter((r) => r.isActive !== target).length;
}

/** The rows that failed, so they stay selected after the action. */
export function failedIds(result: BulkStatusResult | BulkDeleteResult): Set<string> {
  return new Set(result.results.filter((r) => !r.ok).map((r) => r.id));
}

const plural = (n: number, one: string, many: string): string => `${n} ${n === 1 ? one : many}`;

/** "3 employees deactivated, 1 already inactive, 2 not changed." */
export function resultSummary(
  result: BulkStatusResult | BulkDeleteResult,
  action: BulkAction,
  noun: { one: string; many: string },
): string {
  const verb = { activate: "activated", deactivate: "deactivated", delete: "deleted" }[action];
  const parts: string[] = [];
  if ("deleted" in result) {
    parts.push(`${plural(result.deleted, noun.one, noun.many)} ${verb}`);
  } else {
    const changed = result.results.filter((r) => r.ok && r.changed).length;
    const already = result.succeeded - changed;
    parts.push(`${plural(changed, noun.one, noun.many)} ${verb}`);
    if (already > 0) {
      parts.push(`${already} already ${action === "activate" ? "active" : "inactive"}`);
    }
    if (result.employees_deactivated) {
      parts.push(
        `${plural(result.employees_deactivated, "employee", "employees")} deactivated with them`,
      );
    }
  }
  if (result.failed > 0) parts.push(`${result.failed} not changed`);
  return `${parts.join(", ")}.`;
}
