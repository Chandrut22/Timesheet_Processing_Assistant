import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";

// The client is tested against a fake session and a fake network adapter.
const state = vi.hoisted(() => ({
  token: "old" as string | null,
  refreshCalls: 0,
  refreshOk: true,
  backendDown: false,
}));

vi.mock("../src/api/session", () => ({
  getAccessToken: () => state.token,
  refreshAccessToken: async () => {
    state.refreshCalls += 1;
    if (state.backendDown) {
      const { ApiError } = await import("../src/api/errors");
      throw new ApiError({ status: 0, message: "Can't reach the server." });
    }
    if (!state.refreshOk) return null;
    state.token = "new";
    return "new";
  },
}));

const { http } = await import("../src/api/client");
const { ApiError } = await import("../src/api/errors");

type Handler = (config: InternalAxiosRequestConfig) => { status: number; data: unknown };
let seen: { url?: string; auth?: string; withCredentials?: boolean }[] = [];

function useAdapter(handler: Handler) {
  http.defaults.adapter = async (config) => {
    seen.push({
      url: config.url,
      auth: String(config.headers.get("Authorization") ?? ""),
      withCredentials: config.withCredentials,
    });
    const { status, data } = handler(config);
    const response: AxiosResponse = { status, data, headers: {}, statusText: "", config };
    if (status >= 400) throw new AxiosError("fail", "ERR_BAD_REQUEST", config, null, response);
    return response;
  };
}

beforeEach(() => {
  state.token = "old";
  state.refreshCalls = 0;
  state.refreshOk = true;
  state.backendDown = false;
  seen = [];
});

describe("http client", () => {
  it("adds the bearer token, and cookies only for /auth", async () => {
    useAdapter(() => ({ status: 200, data: {} }));
    await http.get("/api/me");
    await http.post("/auth/change-password", {});
    expect(seen[0]).toMatchObject({ auth: "Bearer old" });
    expect(seen[0].withCredentials).toBeFalsy();
    expect(seen[1].withCredentials).toBe(true);
  });

  it("on 401 refreshes once and retries with the new token", async () => {
    useAdapter((c) =>
      String(c.headers.get("Authorization")) === "Bearer new"
        ? { status: 200, data: { ok: true } }
        : { status: 401, data: {} },
    );
    const res = await http.get("/api/timesheets");
    expect(res.data).toEqual({ ok: true });
    expect(state.refreshCalls).toBe(1);
    expect(seen.map((s) => s.auth)).toEqual(["Bearer old", "Bearer new"]);
  });

  it("does not loop: a second 401 becomes an ApiError", async () => {
    useAdapter(() => ({ status: 401, data: { detail: "Token expired" } }));
    await expect(http.get("/api/timesheets")).rejects.toBeInstanceOf(ApiError);
    expect(state.refreshCalls).toBe(1);
    expect(seen).toHaveLength(2);
  });

  it("gives up when the refresh fails", async () => {
    state.refreshOk = false;
    useAdapter(() => ({ status: 401, data: {} }));
    await expect(http.get("/api/me")).rejects.toMatchObject({ status: 401 });
    expect(seen).toHaveLength(1);
  });

  it("never refreshes for the login call itself", async () => {
    useAdapter(() => ({ status: 401, data: { detail: "Wrong email or password" } }));
    await expect(http.post("/auth/login", {})).rejects.toMatchObject({
      message: "Wrong email or password",
    });
    expect(state.refreshCalls).toBe(0);
  });

  it("maps 409 bodies to their detail", async () => {
    useAdapter(() => ({ status: 409, data: { detail: "Already approved.", code: "conflict" } }));
    await expect(http.post("/api/timesheets/x/approve", {})).rejects.toMatchObject({
      status: 409,
      code: "conflict",
      message: "Already approved.",
    });
  });
});

describe("http client while the backend is unreachable", () => {
  it("fails with a retryable error instead of signing out", async () => {
    state.backendDown = true;
    useAdapter(() => ({ status: 401, data: {} }));
    await expect(http.get("/api/me")).rejects.toMatchObject({ status: 0 });
    expect(state.refreshCalls).toBe(1);
    expect(seen).toHaveLength(1);
  });
});
