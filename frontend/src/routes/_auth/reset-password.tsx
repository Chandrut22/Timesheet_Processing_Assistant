import { createFileRoute } from "@tanstack/react-router";
import { ResetPasswordPage, validateResetPasswordSearch } from "@/features/auth";

export const Route = createFileRoute("/_auth/reset-password")({
  validateSearch: validateResetPasswordSearch,
  component: ResetPasswordPage,
});
