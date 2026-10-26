import { describe, expect, it } from "vitest";
import { nextReviewSearch, parseReviewSearch, reviewParams } from "./search";

describe("review queue URL", () => {
  it("defaults to needs_review, worst severity first", () => {
    const p = reviewParams(parseReviewSearch({}));
    expect(p.status).toEqual(["needs_review"]);
    expect(p.sort).toBe("severity");
    expect(p.order).toBe("desc");
    expect(p.page).toBe(1);
  });

  it("drops bad values instead of sending them", () => {
    const s = parseReviewSearch({
      status: "nope",
      severity: "high",
      page: "0",
      company_id: "x",
      min_conf: 80,
    });
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

  it("a new search goes back to page 1 and keeps sorting and the other filters", () => {
    const prev = { q: "grace", status: "all" as const, sort: "received" as const, page: 4 };
    expect(nextReviewSearch(prev, { q: "hopper" })).toEqual({
      q: "hopper",
      status: "all",
      sort: "received",
    });
    expect(nextReviewSearch(prev, { page: 5 })).toEqual({ ...prev, page: 5 });
  });

  it("clearing the search box drops q, so the list is unfiltered again", () => {
    const next = nextReviewSearch({ q: "grace", severity: "high", page: 2 }, { q: "" });
    expect(next).toEqual({ severity: "high" });
    expect(reviewParams(next).q).toBeUndefined();
  });
});
