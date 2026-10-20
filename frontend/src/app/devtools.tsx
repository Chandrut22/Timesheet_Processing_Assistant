import { lazy, Suspense } from "react";

// Devtools are code-split and only rendered in development, so production
// users never download them.
const QueryDevtoolsLazy = lazy(() =>
  import("@tanstack/react-query-devtools").then((m) => ({ default: m.ReactQueryDevtools })),
);
const RouterDevtoolsLazy = lazy(() =>
  import("@tanstack/react-router-devtools").then((m) => ({ default: m.TanStackRouterDevtools })),
);

export function Devtools() {
  if (!import.meta.env.DEV) return null;
  return (
    <Suspense fallback={null}>
      <QueryDevtoolsLazy buttonPosition="bottom-left" />
    </Suspense>
  );
}

export function RouterDevtools() {
  if (!import.meta.env.DEV) return null;
  return (
    <Suspense fallback={null}>
      <RouterDevtoolsLazy position="bottom-right" />
    </Suspense>
  );
}
