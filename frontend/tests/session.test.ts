import { afterEach, describe, expect, it, vi } from "vitest";

// A fake network for the session's bare axios instance.
type Mode = "ok" | "down" | "error500" | "refused";
const fake = vi.hoisted(() => ({
  mode: "ok" as Mode,
  refreshCalls: 0,
  fail(mode: Mode) {
    if (mode === "down") throw { isAxiosError: true, message: "Network Error", response: undefined };
    const status = mode === "refused" ? 401 : 500;
    throw { isAxiosError: true, message: "fail", response: { status, data: {}, headers: {} } };
  },
  async post(url: string) {
    if (url === "/auth/refresh") {
      fake.refreshCalls += 1;
      await new Promise((r) => setTimeout(r, 10));
      if (fake.mode !== "ok") fake.fail(fake.mode);
      return { data: { access_token: `tok${fake.refreshCalls}`, token_type: "bearer", expires_in: 900 } };
    }
    return { data: {} };
  },
  async get() {
    return { data: { id: "u1", role: "admin", name: "Ada", email: "ada@example.com" } };
  },
}));

vi.mock("axios", async (importOriginal) => {
  const actual = await importOriginal<typeof import("axios")>();
  return { ...actual, default: { ...actual.default, create: () => ({ post: fake.post, get: fake.get }) } };
});

const session = await import("../src/api/session");

afterEach(() => {
  vi.useRealTimers();
});

describe("session", () => {
  it("restores the signed-in user on startup", async () => {
    fake.mode = "ok";
    const s = await session.ensureSession();
    expect(s.status).toBe("authenticated");
    expect(s.user?.role).toBe("admin");
  });

  it("shares one refresh between parallel callers", async () => {
    fake.mode = "ok";
    const before = fake.refreshCalls;
    const results = await Promise.all([1, 2, 3, 4, 5].map(() => session.refreshAccessToken()));
    expect(new Set(results).size).toBe(1);
    expect(fake.refreshCalls - before).toBe(1);
    expect(session.getAccessToken()).toBe(results[0]);
  });

  it("keeps the session on a network error, and retries by itself", async () => {
    vi.useFakeTimers();
    fake.mode = "down";
    const token = session.getAccessToken();
    const attempt = session.refreshAccessToken();
    const check = expect(attempt).rejects.toMatchObject({ status: 0 });
    await vi.advanceTimersByTimeAsync(20);
    await check;
    expect(session.getSession().status).toBe("authenticated");
    expect(session.getAccessToken()).toBe(token);

    // The backend comes back: the scheduled retry (5 s) refreshes the token.
    fake.mode = "ok";
    const calls = fake.refreshCalls;
    await vi.advanceTimersByTimeAsync(5_100);
    expect(fake.refreshCalls).toBe(calls + 1);
    expect(session.getAccessToken()).not.toBe(token);
  });

  it("keeps the session on a 5xx", async () => {
    vi.useFakeTimers();
    fake.mode = "error500";
    const attempt = session.refreshAccessToken();
    const check = expect(attempt).rejects.toMatchObject({ status: 500 });
    await vi.advanceTimersByTimeAsync(20);
    await check;
    expect(session.getSession().status).toBe("authenticated");
  });

  it("signs out when the backend refuses the refresh (401)", async () => {
    vi.useFakeTimers();
    fake.mode = "refused";
    const attempt = session.refreshAccessToken();
    await vi.advanceTimersByTimeAsync(20);
    await expect(attempt).resolves.toBeNull();
    expect(session.getAccessToken()).toBeNull();
    expect(session.getSession().status).toBe("anonymous");
  });

  it("forgets the token on logout", async () => {
    fake.mode = "ok";
    await session.login("ada@example.com", "secret123");
    expect(session.getAccessToken()).not.toBeNull();
    await session.logout();
    expect(session.getAccessToken()).toBeNull();
    expect(session.getSession().status).toBe("anonymous");
  });
});
