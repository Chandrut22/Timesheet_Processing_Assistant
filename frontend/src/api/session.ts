// The signed-in session. The access token lives ONLY in this module's memory
// (never localStorage). The refresh token is an httpOnly cookie (Path=/auth)
// that the browser sends to /auth/refresh by itself.
//
// Refresh failures are split in two:
//   - the backend refuses (401, or any other 4xx): the session is over -> sign out
//   - network error or 5xx (backend restarting mid-demo): keep the session,
//     retry shortly, and let the failed request surface as a "can't reach the
//     server" error that TanStack Query retries.
import axios, { isAxiosError } from "axios";
import { toApiError } from "./errors";
import type { PrincipalRead, TokenResponse } from "./models";

export type SessionUser = PrincipalRead;
export type SessionState =
  | { status: "unknown"; user: null }
  | { status: "authenticated"; user: SessionUser }
  | { status: "anonymous"; user: null };

/** Bare instance: no interceptors, so refresh and login can never loop. */
const bare = axios.create({ withCredentials: true });

const RETRY_DELAYS_MS = [5_000, 10_000, 20_000, 40_000, 60_000];
const BOOT_DELAYS_MS = [1_000, 2_000, 4_000];

let state: SessionState = { status: "unknown", user: null };
let accessToken: string | null = null;
let refreshTimer: ReturnType<typeof setTimeout> | undefined;
let retryAttempt = 0;
let refreshPromise: Promise<string | null> | null = null;
let bootPromise: Promise<SessionState> | null = null;
const listeners = new Set<() => void>();

function setState(next: SessionState) {
  state = next;
  listeners.forEach((l) => l());
}

export function subscribeSession(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
export const getSession = (): SessionState => state;
export const getAccessToken = (): string | null => accessToken;

/** True when the server answered and said no. Retrying can't fix these. */
export function isRefusal(err: unknown): boolean {
  if (!isAxiosError(err) || !err.response) return false;
  return err.response.status >= 400 && err.response.status < 500;
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

function schedule(ms: number) {
  if (refreshTimer) clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => {
    // Errors are handled inside (sign-out or another retry); nothing to surface here.
    refreshAccessToken().catch(() => undefined);
  }, ms);
}

function applyToken(token: TokenResponse) {
  accessToken = token.access_token;
  retryAttempt = 0;
  // Refresh about 60 s before the token expires (never sooner than 10 s from now).
  schedule(Math.max((token.expires_in - 60) * 1000, 10_000));
}

/** After a network error / 5xx: try again soon, backing off up to a minute. */
function scheduleRetry() {
  if (state.status !== "authenticated") return;
  schedule(RETRY_DELAYS_MS[Math.min(retryAttempt, RETRY_DELAYS_MS.length - 1)]);
  retryAttempt += 1;
}

async function fetchMe(): Promise<SessionUser> {
  const res = await bare.get<PrincipalRead>("/api/me", {
    headers: { Authorization: `Bearer ${accessToken}` },
    withCredentials: false,
  });
  return res.data;
}

export function clearSession() {
  accessToken = null;
  retryAttempt = 0;
  if (refreshTimer) clearTimeout(refreshTimer);
  refreshTimer = undefined;
  if (state.status !== "anonymous") setState({ status: "anonymous", user: null });
}

/**
 * One shared refresh at a time: five parallel 401s cause one call to /auth/refresh.
 * - resolves to the new token on success
 * - resolves to null (and signs out) when the backend refuses
 * - rejects with an ApiError on a network error / 5xx; the session is kept and
 *   a retry is scheduled
 */
export function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;
  const p = bare
    .post<TokenResponse>("/auth/refresh")
    .then((res) => {
      applyToken(res.data);
      return accessToken;
    })
    .catch(async (err: unknown) => {
      if (isRefusal(err)) {
        clearSession();
        return null;
      }
      scheduleRetry();
      throw await toApiError(err);
    })
    .finally(() => {
      refreshPromise = null;
    });
  refreshPromise = p;
  return p;
}

/**
 * Called before every protected route: restores the session once after a reload.
 * If the backend can't be reached it retries a few times, then rejects (the
 * router shows "Can't reach the server" with a retry button) instead of sending
 * you to the login page.
 */
export function ensureSession(): Promise<SessionState> {
  if (state.status !== "unknown") return Promise.resolve(state);
  if (!bootPromise) {
    bootPromise = (async (): Promise<SessionState> => {
      for (let attempt = 0; ; attempt++) {
        try {
          const token = await refreshAccessToken();
          if (!token) {
            setState({ status: "anonymous", user: null });
            return state;
          }
          const user = await fetchMe();
          setState({ status: "authenticated", user });
          return state;
        } catch (err) {
          if (isRefusal(err)) {
            clearSession();
            return state;
          }
          if (attempt >= BOOT_DELAYS_MS.length) throw await toApiError(err);
          await wait(BOOT_DELAYS_MS[attempt]);
        }
      }
    })().finally(() => {
      bootPromise = null;
    });
  }
  return bootPromise;
}

export async function login(email: string, password: string): Promise<SessionUser> {
  try {
    const res = await bare.post<TokenResponse>("/auth/login", { email, password });
    applyToken(res.data);
    const user = await fetchMe();
    setState({ status: "authenticated", user });
    return user;
  } catch (err) {
    accessToken = null;
    if (refreshTimer) clearTimeout(refreshTimer);
    throw await toApiError(err);
  }
}

export async function logout(): Promise<void> {
  try {
    await bare.post("/auth/logout");
  } catch {
    // Logging out locally is what matters; the cookie expires on its own.
  }
  clearSession();
}
