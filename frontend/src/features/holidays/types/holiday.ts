import { z } from "zod";
import { isoDate, isoDateTime, uuid } from "@/services/schemas";

export const HolidayReadSchema = z.object({
  id: uuid,
  company_id: uuid.nullable(),
  holiday_date: isoDate,
  name: z.string(),
  /** Inactive holidays stay listed but no longer count when pay is calculated. */
  is_active: z.boolean(),
  created_at: isoDateTime,
});

export type HolidayRead = z.infer<typeof HolidayReadSchema>;

export type HolidayCreate = { company_id?: string | null; holiday_date: string; name: string };

export type HolidayListParams = { company_id?: string; year?: number; is_active?: boolean };
