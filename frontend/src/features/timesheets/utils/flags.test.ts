import { describe, expect, it } from "vitest";
import { flagLabel, matchMethodLabel } from "./flags";
import { flagCandidates } from "./severity";

describe("close-spelling labels", () => {
  it("names the flag and the match method", () => {
    expect(flagLabel("fuzzy_match")).toBe("Close spelling");
    expect(matchMethodLabel("fuzzy")).toBe("Close spelling (check it)");
    expect(matchMethodLabel("code")).toBe("Code");
    expect(matchMethodLabel(null)).toBe("—");
  });

  it("shows the company and spelling score of a suggestion", () => {
    const flags = [
      {
        code: "no_company",
        message: "",
        severity: "high",
        candidates: [
          { id: "e7", name: "John Smith", code: "E7", company: "Lakeside", spelling: 0.89 },
        ],
      },
    ] as never;
    expect(flagCandidates(flags)).toEqual([
      { id: "e7", label: "John Smith (E7) · Lakeside · spelling 89%" },
    ]);
  });
});
