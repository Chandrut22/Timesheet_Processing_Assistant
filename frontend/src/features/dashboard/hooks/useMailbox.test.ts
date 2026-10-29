import { describe, expect, it, vi } from "vitest";
import type { MailboxCheck } from "../types/mailbox";

vi.mock("../services/mailboxService", () => ({ mailboxService: {} }));
const { followCheck } = await import("./useMailbox");

const check = (state: MailboxCheck["state"]): MailboxCheck => ({ request_id: "r1", state });
const noWait = (): Promise<void> => Promise.resolve();

describe("followCheck", () => {
  it("asks until the check is done", async () => {
    const get = vi
      .fn()
      .mockResolvedValueOnce(check("queued"))
      .mockResolvedValueOnce(check("running"))
      .mockResolvedValueOnce({ ...check("done"), found: 2 });
    const result = await followCheck("r1", get, noWait);
    expect(result?.state).toBe("done");
    expect(get).toHaveBeenCalledTimes(3);
  });

  it("stops at failed", async () => {
    const get = vi.fn().mockResolvedValue({ ...check("failed"), error: "IMAP login failed" });
    expect((await followCheck("r1", get, noWait))?.error).toBe("IMAP login failed");
  });

  it("gives up after the time limit", async () => {
    const get = vi.fn().mockResolvedValue(check("running"));
    expect(await followCheck("r1", get, noWait, 2_000, 10_000)).toBeNull();
    expect(get).toHaveBeenCalledTimes(5);
  });
});
