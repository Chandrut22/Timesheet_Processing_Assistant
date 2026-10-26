import { z } from "zod";
import { isoDate, isoDateTime, pageOf, uuid } from "@/services/schemas";

export const EmployeeReadSchema = z.object({
  id: uuid,
  company_id: uuid,
  employee_code: z.string(),
  full_name: z.string(),
  email: z.string().nullable(),
  aliases: z.array(z.string()),
  assignment_start: isoDate.nullable(),
  assignment_end: isoDate.nullable(),
  is_active: z.boolean(),
  created_at: isoDateTime,
  updated_at: isoDateTime,
});

export const EmployeePageSchema = pageOf(EmployeeReadSchema);

export type EmployeeRead = z.infer<typeof EmployeeReadSchema>;

export type EmployeeCreate = {
  company_id: string;
  employee_code: string;
  full_name: string;
  email?: string | null;
  aliases?: string[];
  assignment_start?: string | null;
  assignment_end?: string | null;
};

export type EmployeeUpdate = {
  employee_code?: string | null;
  full_name?: string | null;
  email?: string | null;
  aliases?: string[] | null;
  assignment_start?: string | null;
  assignment_end?: string | null;
  is_active?: boolean | null;
};

export type EmployeeListParams = {
  company_id?: string;
  q?: string;
  is_active?: boolean;
  page?: number;
  size?: number;
};
