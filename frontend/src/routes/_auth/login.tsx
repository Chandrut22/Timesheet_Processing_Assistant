import { createFileRoute } from "@tanstack/react-router";
import { LoginPage, validateLoginSearch } from "@/features/auth";

export const Route = createFileRoute("/_auth/login")({
  validateSearch: validateLoginSearch,
  component: LoginPage,
});
