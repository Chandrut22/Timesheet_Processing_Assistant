import { createFileRoute } from "@tanstack/react-router";
import { UsersPage } from "@/features/users";
import { requireAdmin } from "@/features/auth";

export const Route = createFileRoute("/_app/admin/users")({
  beforeLoad: requireAdmin,
  component: UsersPage,
});
