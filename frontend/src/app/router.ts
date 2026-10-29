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
