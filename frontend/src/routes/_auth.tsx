import { createFileRoute, redirect } from "@tanstack/react-router";
import { ensureSession } from "@/api/session";
import { AuthLayout, AuthPending } from "@/features/auth/AuthLayout";

// Public pages (login, forgot / reset password). Signed-in users go to the dashboard.
export const Route = createFileRoute("/_auth")({
  beforeLoad: async () => {
    // If the backend can't be reached, still show the login form.
    const session = await ensureSession().catch(() => null);
    if (session?.status === "authenticated") throw redirect({ to: "/" });
  },
  // While the session check runs, show the background at once (not a blank page).
  pendingComponent: AuthPending,
  pendingMs: 0,
  pendingMinMs: 0,
  component: () => <AuthLayout />,
});
