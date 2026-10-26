import { cleanParams, http } from "@/lib/axios";
import {
  UserPageSchema,
  UserReadSchema,
  type UserCreate,
  type UserUpdate,
  type UserListParams,
} from "../types/user";
import { BulkStatusResultSchema } from "@/services/schemas";
import { responseOf } from "@/services/response";

export const userService = {
  /** `signal` lets TanStack Query cancel a search that a newer one replaced. */
  listUsers: (params: UserListParams, signal?: AbortSignal) =>
    http.get("/users", { params: cleanParams(params), signal }).then(responseOf(UserPageSchema)),
  createUser: (body: UserCreate) => http.post("/users", body).then(responseOf(UserReadSchema)),
  updateUser: (id: string, body: UserUpdate) =>
    http.patch(`/users/${id}`, body).then(responseOf(UserReadSchema)),
  setUserPassword: (id: string, newPassword: string) =>
    http.put(`/users/${id}/password`, { new_password: newPassword }).then(() => undefined),
  /** Admin: activate / deactivate up to 100 users (never yourself, never the last admin). */
  bulkUserStatus: (ids: string[], isActive: boolean) =>
    http
      .post("/users/bulk/status", { ids, is_active: isActive })
      .then(responseOf(BulkStatusResultSchema)),
};
