import { describe, expect, it } from "vitest";
import { IGNORED_NOT_READ, canFetchFromMailbox, fetchesFromMailbox, stepLabel } from "./refetch";

const doc = (id: string, status: string, error: string | null = null, filename = `${id}.csv`) =>
  ({ id, status, error, filename }) as never;

const email = (over: Record<string, unknown> = {}) =>
  ({
    source: "email",
    status: "processed",
    refetch_blocked: null,
    documents: [doc("a", "parsed"), doc("b", "failed", "The file expired")],
    ...over,
  }) as never;

describe("fetching from the mailbox", () => {
  it("happens by itself for a failed file or an ignored email", () => {
    expect(fetchesFromMailbox(email(), null)).toBe(true);
    expect(fetchesFromMailbox(email(), "a")).toBe(false); // that file's text is saved
    expect(fetchesFromMailbox(email(), "b")).toBe(true);
    expect(
      fetchesFromMailbox(
        email({ status: "ignored", documents: [doc("a", "unsupported", IGNORED_NOT_READ)] }),
        null,
      ),
    ).toBe(true);
  });

  it("never for uploads or when the server cannot", () => {
    expect(fetchesFromMailbox(email({ source: "upload" }), null)).toBe(false);
    expect(fetchesFromMailbox(email({ refetch_blocked: "turned off" }), null)).toBe(false);
    expect(canFetchFromMailbox(email())).toBe(true);
    expect(canFetchFromMailbox(email({ source: "upload" }))).toBe(false);
    expect(canFetchFromMailbox(email({ refetch_blocked: "turned off" }))).toBe(false);
  });

  it("names the step", () => {
    expect(stepLabel("fetch")).toBe("Fetch from mailbox");
    expect(stepLabel("read")).toBeNull();
  });
});
