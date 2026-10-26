// Typed build-time settings, read once here so the rest of the app never touches
// import.meta.env directly. The frontend has no VITE_* settings of its own: API targets
// are set on the dev proxy (vite.config.ts, AUTH_URL / CORE_URL in .env), never here.

export const env = {
  /** `npm run dev`. */
  isDev: import.meta.env.DEV,
  /** Vitest. */
  isTest: import.meta.env.MODE === "test",
  /** A production build (`npm run build`). */
  isProd: import.meta.env.PROD,
} as const;
