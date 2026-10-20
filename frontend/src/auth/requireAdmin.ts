import { redirect } from "@tanstack/react-router";
import type { SessionUser } from "@/api/session";

/** Use in an admin route's beforeLoad. Reviewers are sent to the dashboard. */
export function requireAdmin({ context }: { context: { user: SessionUser } }) {
  if (context.user.role !== "admin") throw redirect({ to: "/" });
}
