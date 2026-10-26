import { createRouter } from "@tanstack/react-router";
import { routeTree } from "@/app/routeTree.gen";
import { queryClient } from "@/app/queryClient";

export const router = createRouter({
  routeTree,
  context: { queryClient },
  defaultPreload: "intent",
  defaultPreloadStaleTime: 0,
  scrollRestoration: true,
});

declare module "@tanstack/react-router" {
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
