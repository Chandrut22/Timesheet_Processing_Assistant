import { createFileRoute } from "@tanstack/react-router";
import { ResetPasswordPage } from "@/features/auth/components/ResetPasswordPage";
import { validateResetPasswordSearch } from "@/features/auth/utils/resetPasswordSearch";

export const Route = createFileRoute("/_auth/reset-password")({
  validateSearch: validateResetPasswordSearch,
  component: ResetPasswordPage,
});
