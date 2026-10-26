import type { HolidayListParams } from "../types/holiday";

/** Query keys for holidays. */
export const holidayKeys = {
  all: ["holidays"] as const,
  list: (p: HolidayListParams) => ["holidays", "list", p] as const,
};
