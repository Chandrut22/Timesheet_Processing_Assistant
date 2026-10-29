import type { HolidayBulkResult } from "../types/holiday";

/**
 * "Added to 2 companies. Skipped 1: Hillview already has 'Noel' on this date."
 * `noun` is what was added ("company" for one date, "holiday" for a copy).
 */
export function describeBulkResult(
  result: HolidayBulkResult,
  companyName: (id: string) => string,
  noun: { one: string; many: string } = { one: "company", many: "companies" },
): string {
  const added =
    result.created === 0
      ? "Nothing new to add."
      : `Added ${result.created} ${result.created === 1 ? noun.one : noun.many}.`;
  if (result.skipped.length === 0) return added;
  const shown = result.skipped
    .slice(0, 3)
    .map((s) => `${companyName(s.company_id)}: ${s.reason}`)
    .join(" ");
  const more = result.skipped.length > 3 ? ` (and ${result.skipped.length - 3} more)` : "";
  return `${added} Skipped ${result.skipped.length}. ${shown}${more}`;
}
