// auth-service types. Responses: inferred from ../schemas/auth. Requests: written here,
// mirroring backend/auth-service/src/schemas/ (they are never parsed at runtime).
import type { z } from "zod";
import type {
  MessageResponseSchema,
  TokenResponseSchema,
  UserPageSchema,
  UserReadSchema,
} from "../schemas/auth";
import type { RoleName } from "./common";

export type TokenResponse = z.infer<typeof TokenResponseSchema>;
export type MessageResponse = z.infer<typeof MessageResponseSchema>;
export type UserRead = z.infer<typeof UserReadSchema>;
export type UserPage = z.infer<typeof UserPageSchema>;

export type UserCreate = { name: string; email: string; password: string; role: RoleName };
export type UserUpdate = {
  name?: string | null;
  role?: RoleName | null;
  is_active?: boolean | null;
};
