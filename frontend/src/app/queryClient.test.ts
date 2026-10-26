import { describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { error: () => undefined } }));

const { shouldRetry } = await import("./queryClient");
const { ApiError } = await import("@/services/apiErrors");

const error = (status: number, code: string | null = null) =>
  new ApiError({ status, message: "x", code });

describe("query retries", () => {
  it("retries network failures and 5xx, at most twice", () => {
    expect(shouldRetry(0, error(0))).toBe(true);
    expect(shouldRetry(1, error(502))).toBe(true);
    expect(shouldRetry(2, error(502))).toBe(false);
  });

  it("never retries 4xx, a 429 above all", () => {
    expect(shouldRetry(0, error(404))).toBe(false);
    expect(shouldRetry(0, error(429, "rate_limited"))).toBe(false);
    expect(shouldRetry(0, error(503, "rate_limit_unavailable"))).toBe(false);
  });

  it("never retries a search that a newer one replaced", () => {
    expect(shouldRetry(0, error(0, "cancelled"))).toBe(false);
  });
});
