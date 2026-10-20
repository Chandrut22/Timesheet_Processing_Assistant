import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { ensureSession } from "@/api/session";

// Public pages (login, forgot / reset password). Signed-in users go to the dashboard.
export const Route = createFileRoute("/_auth")({
  beforeLoad: async () => {
    // If the backend can't be reached, still show the login form.
    const session = await ensureSession().catch(() => null);
    if (session?.status === "authenticated") throw redirect({ to: "/" });
  },
  component: AuthLayout,
});

function AuthLayout() {
  return (
    <div className="grid min-h-dvh place-items-center bg-[radial-gradient(ellipse_at_top,var(--color-accent),var(--color-background)_60%)] px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2">
          <span className="grid size-8 place-items-center rounded-md bg-sidebar text-sm font-bold text-white">
            T
          </span>
          <span className="text-base font-semibold tracking-tight">Timesheet Assistant</span>
        </div>
        <div className="rounded-lg border bg-card p-6 shadow-sm">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
