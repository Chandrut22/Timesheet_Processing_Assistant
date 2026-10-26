import type { UserListParams } from "../types/user";

/** Query keys for users. */
export const userKeys = {
  all: ["users"] as const,
  list: (p: UserListParams) => ["users", "list", p] as const,
};
