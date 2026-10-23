// Photos / scans read by the vision model: the new document fields, the chip on
// documents and the readable flag names.
import { describe, expect, it } from "vitest";
import fixtures from "./fixtures/api-responses.json";
import { DocumentReadSchema } from "../src/api/schemas/core";
import { flagLabel } from "../src/lib/flags";
import { hasHandwrittenHours, writingChip } from "../src/lib/writing";

const typed = fixtures.core.submissionPage.items[0].documents[0];
const photo = {
  ...typed,
  read_method: "vision",
  unclear_marks: 2,
  writing_class: "mixed",
  writing_confidence: 0.92,
  has_handwritten_hours: true,
  writing_reason: "Printed table, hours in pen",
};

describe("document fields", () => {
  it("parse for a photo and for a typed document", () => {
    const doc = DocumentReadSchema.parse(photo);
    expect([doc.writing_class, doc.has_handwritten_hours, doc.unclear_marks]).toEqual([
      "mixed",
      true,
      2,
    ]);
    expect(DocumentReadSchema.parse(typed).writing_class).toBeNull();
  });

  it("accept documents read before the fields existed, and refuse unknown classes", () => {
    const old = Object.fromEntries(
      Object.entries(typed).filter(([k]) => !k.startsWith("writing") && k !== "unclear_marks"),
    );
    const parsed = DocumentReadSchema.parse({ ...old, read_method: null });
    expect([parsed.unclear_marks, parsed.has_handwritten_hours]).toEqual([0, false]);
    expect(DocumentReadSchema.safeParse({ ...photo, writing_class: "scribbles" }).success).toBe(
      false,
    );
  });
});

describe("writing chip", () => {
  it("names how the photo / scan is written", () => {
    const doc = DocumentReadSchema.parse(photo);
    expect(writingChip(doc)?.label).toBe("Mixed (handwritten hours)");
    expect(writingChip(doc)?.title).toContain("92% sure");
    expect(
      writingChip({ ...doc, writing_class: "printed_only", has_handwritten_hours: false })?.label,
    ).toBe("Printed");
    expect(writingChip({ ...doc, writing_class: "handwritten_only" })?.label).toBe("Handwritten");
    expect(writingChip({ ...doc, writing_class: "uncertain" })?.tone).toBe("danger");
  });

  it("is not shown for typed documents", () => {
    expect(writingChip(DocumentReadSchema.parse(typed))).toBeNull();
    expect(hasHandwrittenHours(DocumentReadSchema.parse(typed))).toBe(false);
    expect(hasHandwrittenHours(DocumentReadSchema.parse(photo))).toBe(true);
  });

  it("gives the new flags readable names", () => {
    expect(flagLabel("handwritten_hours")).toBe("Handwritten hours");
    expect(flagLabel("unreadable_values")).toBe("Unreadable values");
    expect(flagLabel("writing_unclear")).toBe("Hard to read");
    expect(flagLabel("total_mismatch")).toBe("Total mismatch");
  });
});
