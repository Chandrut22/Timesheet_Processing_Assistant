import { z } from "zod";
import { isoDateTime, pageOf, uuid } from "@/services/schemas";
import type { RoleName } from "@/types/api";

export const UserReadSchema = z.object({
  id: uuid,
  name: z.string(),
  email: z.string(),
  role: z.string(),
  is_active: z.boolean(),
  last_login_at: isoDateTime.nullable(),
  created_at: isoDateTime,
});

export const UserPageSchema = pageOf(UserReadSchema);

export type UserRead = z.infer<typeof UserReadSchema>;

export type UserPage = z.infer<typeof UserPageSchema>;

export type UserCreate = { name: string; email: string; password: string; role: RoleName };

export type UserUpdate = {
  name?: string | null;
  role?: RoleName | null;
  is_active?: boolean | null;
};

export type UserListParams = {
  role?: RoleName;
  is_active?: boolean;
  q?: string;
  page?: number;
  size?: number;
};
