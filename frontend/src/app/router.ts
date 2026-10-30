import { createRouter } from "@tanstack/react-router";
import { routeTree } from "@/app/routeTree.gen";
import { queryClient } from "@/app/queryClient";
import { PagePending } from "@/components/common/PagePending";

export const router = createRouter({
  routeTree,
  context: { queryClient },
  defaultPreload: "intent",
  defaultPreloadStaleTime: 0,
  // Each page is its own chunk (autoCodeSplitting in vite.config.ts). While one loads,
  // show a page outline after 1 s (TanStack's default), for at least 300 ms so it doesn't
  // flash. Hovering a link already starts loading it (defaultPreload: "intent").
  defaultPendingComponent: PagePending,
  defaultPendingMinMs: 300,
  scrollRestoration: true,
});
