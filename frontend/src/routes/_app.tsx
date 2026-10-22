import {
  createFileRoute,
  Outlet,
  redirect,
  useLocation,
  useNavigate,
} from "@tanstack/react-router";
import { useEffect, useRef } from "react";
import { ensureSession } from "@/api/session";
import { useSession } from "@/auth/useSession";
import { AppShell } from "@/components/AppShell";

const AUTH_PATHS = ["/login", "/forgot-password", "/reset-password"];
const MAX_RETURN_LENGTH = 1000;

/** Where to come back to after signing in. Never an auth page, so it can't nest. */
function returnTo(pathname: string, searchStr: string): string | undefined {
  if (AUTH_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`))) return undefined;
  const target = `${pathname}${searchStr}`;
  return target.length > MAX_RETURN_LENGTH ? undefined : target;
}

// Every signed-in page lives under this layout. It restores the session after a
// reload (POST /auth/refresh) and sends anonymous visitors to /login.
export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ location }) => {
    const session = await ensureSession();
    if (session.status !== "authenticated") {
      throw redirect({
        to: "/login",
        search: { redirect: returnTo(location.pathname, location.searchStr) },
        replace: true,
      });
    }
    return { user: session.user };
  },
  component: AppLayout,
});

function AppLayout() {
  const session = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const leaving = useRef(false);

  // The session can end while you're on a page (sign out, or the refresh token expired).
  // Redirect once: this layout can re-render while the router is still leaving the page,
  // and redirecting again from /login is what built the endless ?redirect=... chain.
  useEffect(() => {
    if (session.status !== "anonymous" || leaving.current) return;
    leaving.current = true;
    void navigate({
      to: "/login",
      search: { redirect: returnTo(location.pathname, location.searchStr) },
      replace: true,
    });
  }, [session.status, navigate, location.pathname, location.searchStr]);

  if (session.status !== "authenticated") return null;
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}
