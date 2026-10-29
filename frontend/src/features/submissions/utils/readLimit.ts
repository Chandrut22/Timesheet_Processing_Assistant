// Turns DocumentRead.read_limit into a short line like "Read pages 1–50 of 100"
// or "2 sheets not read". It accepts the shapes a backend is likely to send
// (a plain message, or an object with page / sheet / row counts) and returns
// null when nothing was cut off. Unit-tested in readLimit.test.ts.

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

function first(obj: Record<string, unknown>, keys: string[]): unknown {
  for (const k of keys) if (obj[k] !== undefined && obj[k] !== null) return obj[k];
  return undefined;
}

const plural = (n: number, word: string): string => `${n} ${word}${n === 1 ? "" : "s"}`;

export function describeReadLimit(limit: unknown): string | null {
  if (limit === null || limit === undefined || limit === false) return null;
  if (typeof limit === "string") return limit.trim() || null;
  if (typeof limit !== "object" || Array.isArray(limit)) return null;
  const o = limit as Record<string, unknown>;

  const parts: string[] = [];

  const pagesRead = num(first(o, ["pages_read", "read_pages", "max_pages", "page_limit", "pages"]));
  const pagesTotal = num(first(o, ["total_pages", "pages_total", "page_count"]));
  if (pagesRead !== null && pagesTotal !== null && pagesRead < pagesTotal) {
    parts.push(`Read pages 1–${pagesRead} of ${pagesTotal}`);
  } else if (pagesRead !== null && pagesTotal === null) {
    parts.push(`Read the first ${plural(pagesRead, "page")}`);
  }

  const skipped = first(o, [
    "sheets_skipped",
    "skipped_sheets",
    "sheets_not_read",
    "unread_sheets",
  ]);
  const skippedCount = Array.isArray(skipped) ? skipped.length : num(skipped);
  const sheetsRead = num(first(o, ["sheets_read", "read_sheets", "max_sheets", "sheet_limit"]));
  const sheetsTotal = num(first(o, ["total_sheets", "sheets_total", "sheet_count"]));
  const notRead =
    skippedCount ??
    (sheetsRead !== null && sheetsTotal !== null ? Math.max(0, sheetsTotal - sheetsRead) : null);
  if (notRead) {
    const names =
      Array.isArray(skipped) && skipped.every((s) => typeof s === "string")
        ? ` (${skipped.join(", ")})`
        : "";
    parts.push(`${plural(notRead, "sheet")} not read${names}`);
  }

  const rowsRead = num(first(o, ["rows_read", "max_rows", "row_limit"]));
  const rowsTotal = num(first(o, ["total_rows", "rows_total", "row_count"]));
  if (rowsRead !== null && rowsTotal !== null && rowsRead < rowsTotal) {
    parts.push(`Read ${rowsRead} of ${rowsTotal} rows`);
  }

  if (parts.length > 0) return parts.join(" · ");

  const message = first(o, ["message", "reason", "detail", "note"]);
  if (typeof message === "string" && message.trim()) return message.trim();
  if (o["truncated"] === true || o["limited"] === true) return "Only part of this file was read";
  return null;
}
