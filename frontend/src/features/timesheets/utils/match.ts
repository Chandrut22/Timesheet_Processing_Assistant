import type { TimesheetRead } from "../types/timesheet";

/** Rows whose employee a reviewer can still set: no employee yet, and not exported. */
export function canMatch(t: Pick<TimesheetRead, "status">): boolean {
  return t.status !== "exported";
}

export function isUnmatched(t: Pick<TimesheetRead, "employee_id" | "status">): boolean {
  return t.employee_id === null && canMatch(t);
}

/**
 * The unmatched row to match after `currentId`, in the order on screen: the first one
 * below it, else the first one above it. null when it was the last.
 */
export function nextUnmatched<T extends Pick<TimesheetRead, "id" | "employee_id" | "status">>(
  items: readonly T[],
  currentId: string,
): T | null {
  const at = items.findIndex((t) => t.id === currentId);
  const after = items.slice(at + 1);
  const before = at < 0 ? [] : items.slice(0, at);
  return [...after, ...before].find((t) => t.id !== currentId && isUnmatched(t)) ?? null;
}
