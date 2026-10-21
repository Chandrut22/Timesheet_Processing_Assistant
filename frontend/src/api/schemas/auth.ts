// What auth-service sends back. Source of truth: backend/auth-service/src/schemas/.
import { z } from "zod";
import { int, isoDateTime, pageOf, uuid } from "./common";

export const TokenResponseSchema = z.object({
  access_token: z.string(),
  token_type: z.string(),
  expires_in: int,
});

export const MessageResponseSchema = z.object({ message: z.string() });

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
