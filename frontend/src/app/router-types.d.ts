import type { router } from "./router";

declare module "@tanstack/router-core" {
  interface Register {
    router: typeof router;
  }

  /** Per-route layout options, read by AppShell (`staticData` on a route). */
  interface StaticDataRouteOption {
    /** Full width and full height: no max-width cap, the page owns the viewport
     * (it scrolls its own panels). Used by the Upload page. */
    fullWidth?: boolean;
  }
}
