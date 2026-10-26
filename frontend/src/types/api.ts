import type { z } from "zod";
import {
  BulkDeleteResultSchema,
  BulkStatusItemSchema,
  BulkStatusResultSchema,
  RoleNameSchema,
  PrincipalReadSchema,
  SortOrderSchema,
  TokenResponseSchema,
} from "@/services/schemas";

export type Page<T> = { items: T[]; total: number; page: number; size: number };

export type RoleName = z.infer<typeof RoleNameSchema>;

export type BulkStatusItem = z.infer<typeof BulkStatusItemSchema>;

export type BulkStatusResult = z.infer<typeof BulkStatusResultSchema>;

export type BulkDeleteResult = z.infer<typeof BulkDeleteResultSchema>;

export type Decimal = number | string;

export type SortOrder = z.infer<typeof SortOrderSchema>;

export type PrincipalRead = z.infer<typeof PrincipalReadSchema>;

export type TokenResponse = z.infer<typeof TokenResponseSchema>;
