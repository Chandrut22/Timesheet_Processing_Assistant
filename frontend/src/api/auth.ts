// auth-service endpoints other than login / refresh / logout (those live in session.ts).
// JSON responses are checked against their zod schemas in dev and tests.
import { cleanParams, http } from "./client";
import { MessageResponseSchema, UserPageSchema, UserReadSchema } from "./schemas/auth";
import { responseOf } from "./schemas/common";
import type { RoleName, UserCreate, UserUpdate } from "./models";

export type UserListParams = {
  role?: RoleName;
  is_active?: boolean;
  q?: string;
  page?: number;
  size?: number;
};

export const authApi = {
  forgotPassword: (email: string) =>
    http.post("/auth/forgot-password", { email }).then(responseOf(MessageResponseSchema)),
  resetPassword: (email: string, code: string, newPassword: string) =>
    http
      .post("/auth/reset-password", { email, code, new_password: newPassword })
      .then(responseOf(MessageResponseSchema)),
  changePassword: (currentPassword: string, newPassword: string) =>
    http
      .post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      })
      .then(() => undefined),

  listUsers: (params: UserListParams) =>
    http.get("/users", { params: cleanParams(params) }).then(responseOf(UserPageSchema)),
  createUser: (body: UserCreate) => http.post("/users", body).then(responseOf(UserReadSchema)),
  updateUser: (id: string, body: UserUpdate) =>
    http.patch(`/users/${id}`, body).then(responseOf(UserReadSchema)),
  setUserPassword: (id: string, newPassword: string) =>
    http.put(`/users/${id}/password`, { new_password: newPassword }).then(() => undefined),
};
