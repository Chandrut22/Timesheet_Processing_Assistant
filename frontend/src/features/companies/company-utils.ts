import type { CompanyCreate, CompanyUpdate } from "@/api/models";
import { splitList } from "@/lib/format";
import type { CompanyFormValues } from "./CompanyForm";

/** Rates are sent as strings ("450.00"): the API accepts them and keeps exact decimals. */
export function toCompanyBody(v: CompanyFormValues): CompanyCreate & CompanyUpdate {
  return {
    name: v.name.trim(),
    aliases: splitList(v.aliases),
    currency: v.currency.trim().toUpperCase(),
    hourly_rate: v.hourly_rate,
    overtime_rate: v.overtime_rate,
    double_time_rate: v.double_time_rate || null,
    holiday_rate: v.holiday_rate,
    daily_ot_after: v.daily_ot_after,
    weekly_ot_after: v.weekly_ot_after,
    double_time_after: v.double_time_after || null,
    week_start: Number(v.week_start),
  };
}
