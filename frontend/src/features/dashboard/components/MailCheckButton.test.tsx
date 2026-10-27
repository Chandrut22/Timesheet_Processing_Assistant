// @vitest-environment jsdom
// "Check mail now": hidden when email is off, disabled while the listener is down or in
// the cooldown, and the result message counts what the check found.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MailboxStatus } from "../types/mailbox";
import { describeCheck } from "../utils/describeCheck";
import { MailCheckButton } from "./MailCheckButton";

const getStatus = vi.fn<() => Promise<MailboxStatus>>();
vi.mock("../services/mailboxService", () => ({
  mailboxService: { getStatus: () => getStatus(), checkNow: vi.fn(), getCheck: vi.fn() },
}));

const base: MailboxStatus = {
  enabled: true,
  running: true,
  connected: true,
  mailbox: "timesheets@x.com",
  last_check_at: new Date().toISOString(),
  last_found: 0,
  last_queued: 0,
  last_ignored: 0,
  last_error: null,
  cooldown_seconds: 0,
};

function show(status: MailboxStatus) {
  getStatus.mockResolvedValue(status);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MailCheckButton />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  getStatus.mockReset();
});

describe("MailCheckButton", () => {
  it("can be pressed while the listener runs", async () => {
    show(base);
    const button = await screen.findByRole("button", { name: /Check mail now/ });
    expect(button.hasAttribute("disabled")).toBe(false);
    expect(screen.getByRole("status").textContent).toMatch(/Email checked/);
  });

  it("is disabled while the listener is not running", async () => {
    show({ ...base, running: false, connected: false, last_error: "IMAP login failed" });
    const button = await screen.findByRole("button", { name: /Check mail now/ });
    expect(button.hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("status").textContent).toMatch(/not running: IMAP login failed/);
  });

  it("counts down the cooldown", async () => {
    show({ ...base, cooldown_seconds: 20 });
    const button = await screen.findByRole("button", { name: /Check mail now \(20s\)/ });
    expect(button.hasAttribute("disabled")).toBe(true);
  });

  it("is hidden when reading email is turned off", async () => {
    const { container } = show({ ...base, enabled: false, running: false });
    await vi.waitFor(() => expect(getStatus).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });
});

describe("describeCheck", () => {
  it("says what the check found", () => {
    const check = { request_id: "1", state: "done" as const };
    expect(describeCheck({ ...check, found: 0 })).toBe("No new email.");
    expect(describeCheck({ ...check, found: 3, queued: 2, ignored: 1 })).toBe(
      "3 new emails: 2 queued for processing, 1 ignored.",
    );
    expect(describeCheck({ ...check, found: 1, queued: 0, duplicates: 1 })).toBe(
      "1 new email: 0 queued for processing, 1 already received.",
    );
  });
});
