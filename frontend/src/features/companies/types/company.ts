import { z } from "zod";
import { decimal, int, isoDateTime, pageOf, uuid } from "@/services/schemas";
import type { Decimal } from "@/types/api";

export const CompanyReadSchema = z.object({
  id: uuid,
  name: z.string(),
  aliases: z.array(z.string()),
  hourly_rate: decimal,
  overtime_rate: decimal,
  double_time_rate: decimal.nullable(),
  holiday_rate: decimal,
  currency: z.string(),
  daily_ot_after: decimal,
  weekly_ot_after: decimal,
  double_time_after: decimal.nullable(),
  week_start: int,
  is_active: z.boolean(),
  created_at: isoDateTime,
  updated_at: isoDateTime,
});

export const CompanyPageSchema = pageOf(CompanyReadSchema);

export const WhitelistReadSchema = z.object({
  id: uuid,
  company_id: uuid,
  kind: z.string(),
  value: z.string(),
  created_at: isoDateTime,
});

export type CompanyRead = z.infer<typeof CompanyReadSchema>;

export type WhitelistRead = z.infer<typeof WhitelistReadSchema>;

export type CompanyCreate = {
  name: string;
  aliases?: string[];
  hourly_rate: Decimal;
  overtime_rate: Decimal;
  double_time_rate?: Decimal | null;
  holiday_rate: Decimal;
  currency: string;
  daily_ot_after: Decimal;
  weekly_ot_after: Decimal;
  double_time_after?: Decimal | null;
  week_start: number;
};

export type CompanyUpdate = {
  name?: string | null;
  aliases?: string[] | null;
  hourly_rate?: Decimal | null;
  overtime_rate?: Decimal | null;
  double_time_rate?: Decimal | null;
  holiday_rate?: Decimal | null;
  currency?: string | null;
  daily_ot_after?: Decimal | null;
  weekly_ot_after?: Decimal | null;
  double_time_after?: Decimal | null;
  week_start?: number | null;
  is_active?: boolean | null;
};

export type CompanyListParams = { q?: string; is_active?: boolean; page?: number; size?: number };
