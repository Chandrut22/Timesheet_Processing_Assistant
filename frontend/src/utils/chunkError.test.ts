import { describe, expect, it } from "vitest";
import { isChunkLoadError } from "./chunkError";

describe("isChunkLoadError", () => {
  it.each([
    "Failed to fetch dynamically imported module: https://app/assets/ExportPage-1a2b.js",
    "error loading dynamically imported module: https://app/assets/x.js",
    "Importing a module script failed.",
    "Unable to preload CSS for /assets/x.css",
  ])("recognises %s", (message) => {
    expect(isChunkLoadError(new TypeError(message))).toBe(true);
  });

  it("recognises a ChunkLoadError by name", () => {
    const e = new Error("Loading chunk 7 failed.");
    e.name = "ChunkLoadError";
    expect(isChunkLoadError(e)).toBe(true);
  });

  it("leaves other errors alone", () => {
    expect(isChunkLoadError(new Error("Not found."))).toBe(false);
    expect(isChunkLoadError("Failed to fetch dynamically imported module")).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
  });
});
