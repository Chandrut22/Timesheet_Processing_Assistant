// auth-service endpoints other than login / refresh / logout (those live in session.ts).
import { cleanParams, http } from "./client";
import type { MessageResponse, Page, RoleName, UserCreate, UserRead, UserUpdate } from "./models";

export type UserListParams = {
  role?: RoleName;
  is_active?: boolean;
  q?: string;
  page?: number;
  size?: number;
};

export const authApi = {
  forgotPassword: (email: string) =>
    http.post<MessageResponse>("/auth/forgot-password", { email }).then((r) => r.data),
  resetPassword: (email: string, code: string, newPassword: string) =>
    http
      .post<MessageResponse>("/auth/reset-password", { email, code, new_password: newPassword })
      .then((r) => r.data),
  changePassword: (currentPassword: string, newPassword: string) =>
    http
      .post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      })
      .then(() => undefined),

  listUsers: (params: UserListParams) =>
    http.get<Page<UserRead>>("/users", { params: cleanParams(params) }).then((r) => r.data),
  createUser: (body: UserCreate) => http.post<UserRead>("/users", body).then((r) => r.data),
  updateUser: (id: string, body: UserUpdate) =>
    http.patch<UserRead>(`/users/${id}`, body).then((r) => r.data),
  setUserPassword: (id: string, newPassword: string) =>
    http.put(`/users/${id}/password`, { new_password: newPassword }).then(() => undefined),
};
