import { describe, expect, it } from "vitest";
import {
  MAX_BYTES,
  extOf,
  fileKind,
  totalBytes,
  validateFiles,
} from "../src/features/ingestion/upload-limits";

/** A File of a given size without allocating it. */
function file(name: string, size = 1000): File {
  const f = new File(["x"], name);
  Object.defineProperty(f, "size", { value: size });
  return f;
}

describe("validateFiles", () => {
  it("accepts supported files", () => {
    const { files, problems } = validateFiles([], [file("a.pdf"), file("b.XLSX"), file("c.jpeg")]);
    expect(files.map((f) => f.name)).toEqual(["a.pdf", "b.XLSX", "c.jpeg"]);
    expect(problems).toEqual([]);
  });

  it("refuses an unsupported type", () => {
    const { files, problems } = validateFiles([], [file("setup.exe")]);
    expect(files).toEqual([]);
    expect(problems).toEqual(["setup.exe: this file type isn't supported."]);
  });

  it("refuses a file over 15 MB", () => {
    const { files, problems } = validateFiles([], [file("big.pdf", MAX_BYTES + 1)]);
    expect(files).toEqual([]);
    expect(problems).toEqual(["big.pdf: larger than 15 MB."]);
    expect(validateFiles([], [file("edge.pdf", MAX_BYTES)]).files).toHaveLength(1);
  });

  it("refuses the 11th file", () => {
    const ten = Array.from({ length: 10 }, (_, i) => file(`f${i}.csv`));
    const { files, problems } = validateFiles(ten, [file("eleven.csv")]);
    expect(files).toHaveLength(10);
    expect(problems).toEqual(["eleven.csv: you can upload at most 10 files at once."]);
  });

  it("skips a duplicate (same name and size) without a message", () => {
    const a = file("a.pdf", 500);
    const { files, problems } = validateFiles([a], [file("a.pdf", 500), file("a.pdf", 501)]);
    expect(files).toHaveLength(2); // the 501-byte one is a different file
    expect(problems).toEqual([]);
  });
});

describe("helpers", () => {
  it("reads extensions, kinds and totals", () => {
    expect(extOf("Week 1.PDF")).toBe(".pdf");
    expect(extOf("noext")).toBe("");
    expect(fileKind("scan.tiff")).toBe("image");
    expect(fileKind("hours.csv")).toBe("text");
    expect(fileKind("sheet.xlsx")).toBe("excel");
    expect(totalBytes([file("a.pdf", 10), file("b.pdf", 32)])).toBe(42);
  });
});
