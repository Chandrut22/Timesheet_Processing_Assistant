import { createRootRouteWithContext, Link, Outlet, useRouter } from "@tanstack/react-router";
import type { QueryClient } from "@tanstack/react-query";
import type { SessionUser } from "@/services/session";
import { RouterDevtools } from "@/app/devtools";
import { ErrorState } from "@/components/common/States";
import { Button } from "@/components/ui/button";
import type { JSX } from "react";

export const Route = createRootRouteWithContext<{
  queryClient: QueryClient;
  user?: SessionUser;
}>()({
  component: RootLayout,
  notFoundComponent: NotFound,
  errorComponent: RootError,
});

function RootError({ error, reset }: { error: unknown; reset: () => void }): JSX.Element {
  const router = useRouter();
  return (
    <div className="mx-auto max-w-xl p-8">
      <ErrorState
        error={error}
        onRetry={() => {
          reset();
          void router.invalidate();
        }}
      />
    </div>
  );
}

function RootLayout(): JSX.Element {
  return (
    <>
      <Outlet />
      <RouterDevtools />
    </>
  );
}

function NotFound(): JSX.Element {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-3 p-10 text-center">
      <p className="text-4xl font-semibold">404</p>
      <p className="text-sm text-muted-foreground">This page doesn't exist.</p>
      <Button asChild variant="outline">
        <Link to="/">Go to the dashboard</Link>
      </Button>
    </div>
  );
}
