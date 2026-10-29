import { cleanParams, http } from "@/lib/axios";
import { BulkDeleteResultSchema, BulkStatusResultSchema } from "@/services/schemas";
import {
  HolidayBulkResultSchema,
  HolidayReadSchema,
  type HolidayBulkCreate,
  type HolidayCopy,
  type HolidayCreate,
  type HolidayListParams,
} from "../types/holiday";
import { z } from "zod";
import { checked } from "@/services/response";

export const holidayService = {
  listHolidays: (params: HolidayListParams) =>
    checked(z.array(HolidayReadSchema), http.get("/api/holidays", { params: cleanParams(params) })),
  createHoliday: (body: HolidayCreate) =>
    checked(HolidayReadSchema, http.post("/api/holidays", body)),
  /** One date and name for several companies (one transaction; existing dates skipped). */
  bulkCreateHolidays: (body: HolidayBulkCreate) =>
    checked(HolidayBulkResultSchema, http.post("/api/holidays/bulk/create", body)),
  copyHolidays: (body: HolidayCopy) =>
    checked(HolidayBulkResultSchema, http.post("/api/holidays/copy", body)),
  deleteHoliday: (id: string) => http.delete(`/api/holidays/${id}`).then(() => undefined),
  bulkHolidayStatus: (ids: string[], isActive: boolean) =>
    checked(
      BulkStatusResultSchema,
      http.post("/api/holidays/bulk/status", { ids, is_active: isActive }),
    ),
  bulkDeleteHolidays: (ids: string[]) =>
    checked(BulkDeleteResultSchema, http.post("/api/holidays/bulk/delete", { ids })),
};
