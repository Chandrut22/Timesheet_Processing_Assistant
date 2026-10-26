import { cleanParams, http } from "@/lib/axios";
import { BulkDeleteResultSchema, BulkStatusResultSchema } from "@/services/schemas";
import { HolidayReadSchema, type HolidayCreate, type HolidayListParams } from "../types/holiday";
import { z } from "zod";
import { checked } from "@/services/response";

export const holidayService = {
  listHolidays: (params: HolidayListParams) =>
    checked(z.array(HolidayReadSchema), http.get("/api/holidays", { params: cleanParams(params) })),
  createHoliday: (body: HolidayCreate) =>
    checked(HolidayReadSchema, http.post("/api/holidays", body)),
  deleteHoliday: (id: string) => http.delete(`/api/holidays/${id}`).then(() => undefined),
  bulkHolidayStatus: (ids: string[], isActive: boolean) =>
    checked(
      BulkStatusResultSchema,
      http.post("/api/holidays/bulk/status", { ids, is_active: isActive }),
    ),
  bulkDeleteHolidays: (ids: string[]) =>
    checked(BulkDeleteResultSchema, http.post("/api/holidays/bulk/delete", { ids })),
};
