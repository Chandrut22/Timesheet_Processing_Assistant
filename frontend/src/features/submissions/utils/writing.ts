// How a photo / scan is written (DocumentRead.writing_class), for the chip on documents.
import type { DocumentRead } from "../types/submission";

export type WritingChip = { label: string; tone: "info" | "warning" | "danger"; title: string };

export function writingChip(
  doc: Pick<
    DocumentRead,
    | "read_method"
    | "writing_class"
    | "has_handwritten_hours"
    | "writing_confidence"
    | "writing_reason"
    | "unclear_marks"
  >,
): WritingChip | null {
  if (doc.read_method !== "vision" || !doc.writing_class) return null;
  const confidence =
    doc.writing_confidence != null ? ` (${Math.round(doc.writing_confidence * 100)}% sure)` : "";
  const unclear = doc.unclear_marks
    ? ` ${doc.unclear_marks} value${doc.unclear_marks === 1 ? "" : "s"} could not be read.`
    : "";
  const title = `Read by an AI vision model${confidence}.${unclear}${doc.writing_reason ? ` ${doc.writing_reason}` : ""}`;
  switch (doc.writing_class) {
    case "printed_only":
      return { label: "Printed", tone: "info", title };
    case "mixed":
      return doc.has_handwritten_hours
        ? { label: "Mixed (handwritten hours)", tone: "warning", title }
        : { label: "Mixed", tone: "info", title };
    case "handwritten_only":
      return { label: "Handwritten", tone: "warning", title };
    default:
      return { label: "Unclear", tone: "danger", title };
  }
}

/** The timesheet came from a document whose hours were written by hand. */
export function hasHandwrittenHours(
  doc: Pick<DocumentRead, "writing_class" | "has_handwritten_hours"> | undefined,
): boolean {
  return !!doc && (doc.has_handwritten_hours || doc.writing_class === "handwritten_only");
}
