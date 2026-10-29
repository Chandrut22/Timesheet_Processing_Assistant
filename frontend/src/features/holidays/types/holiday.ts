import { z } from "zod";
import { isoDate, isoDateTime, uuid } from "@/services/schemas";

export const HolidayReadSchema = z.object({
  id: uuid,
  /** Every holiday belongs to one company. */
  company_id: uuid,
  holiday_date: isoDate,
  name: z.string(),
  /** Inactive holidays stay listed but no longer count when pay is calculated. */
  is_active: z.boolean(),
  created_at: isoDateTime,
});

export type HolidayRead = z.infer<typeof HolidayReadSchema>;

export type HolidayCreate = { company_id: string; holiday_date: string; name: string };

/** The same holiday for several companies (POST /holidays/bulk/create). */
export type HolidayBulkCreate = { company_ids: string[]; holiday_date: string; name: string };

/** Copy one company's holidays to others (POST /holidays/copy). */
export type HolidayCopy = { from_company_id: string; to_company_ids: string[]; year?: number };

export const HolidayBulkResultSchema = z.object({
  created: z.number().int(),
  /** A company that already had a holiday on that date: left as it was. */
  skipped: z.array(z.object({ company_id: uuid, holiday_date: isoDate, reason: z.string() })),
});
export type HolidayBulkResult = z.infer<typeof HolidayBulkResultSchema>;

export type HolidayListParams = { company_id?: string; year?: number; is_active?: boolean };
