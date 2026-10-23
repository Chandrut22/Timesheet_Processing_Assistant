// Readable names for flag codes. Codes not listed here are shown humanized
// ("total_mismatch" -> "Total mismatch"), which reads fine for most of them.
import { humanize } from "./format";

const FLAG_LABELS: Record<string, string> = {
  handwritten_hours: "Handwritten hours",
  unreadable_values: "Unreadable values",
  writing_unclear: "Hard to read",
  handwriting_present: "Some handwriting",
};

export function flagLabel(code: string): string {
  return FLAG_LABELS[code] ?? humanize(code);
}
