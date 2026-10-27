// Readable names for flag codes. Codes not listed here are shown humanized
// ("total_mismatch" -> "Total mismatch"), which reads fine for most of them.
import { humanize } from "@/utils/format";

const FLAG_LABELS: Record<string, string> = {
  handwritten_hours: "Handwritten hours",
  unreadable_values: "Unreadable values",
  writing_unclear: "Hard to read",
  handwriting_present: "Some handwriting",
  fuzzy_match: "Close spelling",
};

const MATCH_METHOD_LABELS: Record<string, string> = {
  fuzzy: "Close spelling (check it)",
  name_reordered: "Name in another order",
  initial_surname: "Initial + surname",
  first_name: "First name only",
};

/** How the employee was matched, for people ("fuzzy" -> "Close spelling (check it)"). */
export function matchMethodLabel(method: string | null | undefined): string {
  return method ? (MATCH_METHOD_LABELS[method] ?? humanize(method)) : "—";
}

export function flagLabel(code: string): string {
  return FLAG_LABELS[code] ?? humanize(code);
}
