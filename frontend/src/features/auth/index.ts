// Public API of the auth feature: other parts of the app import only from here.
export { ForgotPasswordPage } from "./components/ForgotPasswordPage";
export { LoginPage, validateLoginSearch } from "./components/LoginPage";
export { ResetPasswordPage, validateResetPasswordSearch } from "./components/ResetPasswordPage";
export { useIsAdmin, useSession, useUser } from "./hooks/useSession";
export { authService } from "./services/authService";
export { MessageResponseSchema } from "./types/auth";
export { requireAdmin } from "./utils/requireAdmin";
