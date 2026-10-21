import { describe, expect, it } from "vitest";
import { buildApiError, FORBIDDEN_MESSAGE, locToField, SERVER_MESSAGE } from "../src/api/errors";

describe("buildApiError", () => {
  it("shows the backend's own message for app errors", () => {
    const e = buildApiError(409, { detail: "This timesheet is already approved.", code: "conflict" });
    expect(e.status).toBe(409);
    expect(e.code).toBe("conflict");
    expect(e.message).toBe("This timesheet is already approved.");
  });

  it("maps FastAPI validation errors to form fields", () => {
    const e = buildApiError(422, {
      detail: [
        { loc: ["body", "entries", 0, "hours"], msg: "Input should be less than or equal to 24" },
        { loc: ["body", "reason"], msg: "String should have at least 3 characters" },
      ],
    });
    expect(e.fieldErrors["entries.0.hours"]).toBe("Input should be less than or equal to 24");
    expect(e.fieldErrors["reason"]).toBe("String should have at least 3 characters");
    expect(e.message).toBe("Hours: Input should be less than or equal to 24");
  });

  it("keeps a plain 422 message from the app", () => {
    expect(buildApiError(422, { detail: "All days must be in one week." }).message).toBe(
      "All days must be in one week.",
    );
  });

  it("says 'requests' for the per-endpoint rate limit", () => {
    const e = buildApiError(429, { detail: "x", code: "rate_limited" }, "17");
    expect(e.code).toBe("rate_limited");
    expect(e.retryAfter).toBe(17);
    expect(e.message).toBe("Too many requests. Try again in 17 seconds.");
    expect(buildApiError(429, { code: "rate_limited" }, "1").message).toBe(
      "Too many requests. Try again in 1 second.",
    );
  });

  it("explains a 503 from the rate limiter instead of 'something went wrong'", () => {
    const e = buildApiError(503, { detail: "x", code: "rate_limit_unavailable" }, "5");
    expect(e.message).toBe("The service is busy. Please try again in a few seconds.");
    expect(e.retryAfter).toBe(5);
  });

  it("uses Retry-After for 429", () => {
    const e = buildApiError(429, { detail: "Slow down" }, "42");
    expect(e.retryAfter).toBe(42);
    expect(e.message).toBe("Too many attempts. Try again in 42 seconds.");
  });

  it("never shows technical text for 5xx, and a plain message for 403", () => {
    expect(buildApiError(500, { detail: "Traceback (most recent call last)…" }).message).toBe(SERVER_MESSAGE);
    expect(buildApiError(403, { detail: "Forbidden" }).message).toBe(FORBIDDEN_MESSAGE);
  });

  it("turns loc into a react-hook-form path", () => {
    expect(locToField(["body", "entries", 2, "work_date"])).toBe("entries.2.work_date");
    expect(locToField(["query", "size"])).toBe("size");
  });
});
