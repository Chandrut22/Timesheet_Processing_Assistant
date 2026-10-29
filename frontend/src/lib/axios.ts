// THE HTTP CLIENT. Every request the app makes goes through `http` below: screens and
// hooks call the typed feature services (features/*/services), never axios, fetch() or
// XMLHttpRequest directly. ESLint enforces this (eslint.config.js: no-restricted-globals
// / -properties / -imports). Two deliberate exceptions, both in src/services: session.ts
// uses a bare axios instance for login / refresh / logout (no interceptors, so a refresh
// can never trigger another refresh), and apiErrors.ts uses axios only to recognise its
// errors.
import axios, { type InternalAxiosRequestConfig } from "axios";
import { toApiError } from "@/services/apiErrors";
import { getAccessToken, refreshAccessToken } from "@/services/session";

type RetriableConfig = InternalAxiosRequestConfig & { _retry?: boolean };

/**
 * The one HTTP client for the app.
 * - adds the Bearer token
 * - sends cookies only to /auth/* (the refresh cookie lives there)
 * - repeated query params (status=a&status=b), which FastAPI expects for lists
 * - on 401: refresh once (shared), retry once. If the backend refuses the
 *   refresh the session ends; if it can't be reached, the request fails with a
 *   "can't reach the server" ApiError that TanStack Query retries
 * - every error becomes an ApiError with a message that is safe to show
 */
export const http = axios.create({
  paramsSerializer: { indexes: null },
});

const NO_REFRESH = ["/auth/login", "/auth/refresh", "/auth/logout"];

http.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) config.headers.set("Authorization", `Bearer ${token}`);
  if (config.url?.startsWith("/auth")) config.withCredentials = true;
  return config;
});

http.interceptors.response.use(
  (res) => res,
  async (error: unknown) => {
    if (axios.isAxiosError(error) && error.response?.status === 401 && error.config) {
      const config = error.config as RetriableConfig;
      const url = config.url ?? "";
      if (!config._retry && !NO_REFRESH.some((p) => url.startsWith(p))) {
        config._retry = true;
        // Rejects with an ApiError (network / 5xx) while the backend is unreachable.
        const token = await refreshAccessToken();
        if (token) {
          config.headers.set("Authorization", `Bearer ${token}`);
          return http(config);
        }
      }
    }
    throw await toApiError(error);
  },
);

/** Drops empty strings / undefined / null so they are not sent as query params. */
export function cleanParams<T extends Record<string, unknown>>(params: T): Partial<T> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v) && v.length === 0) continue;
    out[k] = v;
  }
  return out as Partial<T>;
}

/** Reads the file name from a Content-Disposition header. */
export function filenameFromDisposition(header: unknown): string | null {
  if (typeof header !== "string") return null;
  const star = /filename\*\s*=\s*(?:UTF-8'')?([^;]+)/i.exec(header);
  if (star) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ""));
    } catch {
      /* fall through */
    }
  }
  const plain = /filename\s*=\s*("?)([^";]+)\1/i.exec(header);
  return plain ? plain[2].trim() : null;
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
