// Public API of the holidays feature: other parts of the app import only from here.
// Pages are not exported: only their route files import them (src/routes), so each
// page stays in its own chunk (autoCodeSplitting).
export { HolidayReadSchema } from "./types/holiday";
export type { HolidayCreate, HolidayListParams } from "./types/holiday";
export { useHolidaysList } from "./hooks/useHolidaysList";
