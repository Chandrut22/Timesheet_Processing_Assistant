import { createFileRoute, Outlet, redirect, useLocation, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { ensureSession } from "@/api/session";
import { useSession } from "@/auth/useSession";
import { AppShell } from "@/components/AppShell";

// Every signed-in page lives under this layout. It restores the session after a
// reload (POST /auth/refresh) and sends anonymous visitors to /login.
export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ location }) => {
    const session = await ensureSession();
    if (session.status !== "authenticated") {
      throw redirect({ to: "/login", search: { redirect: location.href } });
    }
    return { user: session.user };
  },
  component: AppLayout,
});

function AppLayout() {
  const session = useSession();
  const navigate = useNavigate();
  const location = useLocation();

  // The session can end while you're on a page (refresh token expired or revoked).
  useEffect(() => {
    if (session.status === "anonymous") {
      void navigate({ to: "/login", search: { redirect: location.href } });
    }
  }, [session.status, navigate, location.href]);

  if (session.status !== "authenticated") return null;
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}
