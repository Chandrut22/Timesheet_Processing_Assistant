// Public API of the dashboard feature: other parts of the app import only from here.
// Pages are not exported: only their route files import them (src/routes), so each
// page stays in its own chunk (autoCodeSplitting).
export { DashboardSnapshotSchema } from "./types/dashboard";
