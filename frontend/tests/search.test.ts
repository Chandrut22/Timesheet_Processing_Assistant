import { describe, expect, it } from "vitest";
import { parseReviewSearch, reviewParams } from "../src/features/review/search";

describe("review queue URL", () => {
  it("defaults to needs_review, worst severity first", () => {
    const p = reviewParams(parseReviewSearch({}));
    expect(p.status).toEqual(["needs_review"]);
    expect(p.sort).toBe("severity");
    expect(p.order).toBe("desc");
    expect(p.page).toBe(1);
  });

  it("drops bad values instead of sending them", () => {
    const s = parseReviewSearch({ status: "nope", severity: "high", page: "0", company_id: "x", min_conf: 80 });
    expect(s.status).toBeUndefined();
    expect(s.severity).toBe("high");
    expect(s.page).toBeUndefined();
    expect(s.company_id).toBeUndefined();
    expect(reviewParams(s).min_confidence).toBe(0.8);
  });

  it("supports all statuses and matched", () => {
    const p = reviewParams(parseReviewSearch({ status: "all", matched: "no" }));
    expect(p.status).toBeUndefined();
    expect(p.matched).toBe(false);
  });
});
