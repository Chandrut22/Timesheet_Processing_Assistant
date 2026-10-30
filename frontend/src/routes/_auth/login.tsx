import { createFileRoute } from "@tanstack/react-router";
import { LoginPage } from "@/features/auth/components/LoginPage";
import { validateLoginSearch } from "@/features/auth/utils/loginSearch";

export const Route = createFileRoute("/_auth/login")({
  validateSearch: validateLoginSearch,
  component: LoginPage,
});
