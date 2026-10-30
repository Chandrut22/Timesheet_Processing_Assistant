// Public API of the auth feature: other parts of the app import only from here.
// Pages are not exported: only their route files import them (src/routes), so each
// page stays in its own chunk (autoCodeSplitting).
export { useIsAdmin, useSession, useUser } from "./hooks/useSession";
export { useLogout } from "./hooks/useLogout";
export { authService } from "./services/authService";
export { MessageResponseSchema } from "./types/auth";
export { requireAdmin } from "./utils/requireAdmin";
