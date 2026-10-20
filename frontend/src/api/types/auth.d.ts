/**
 * Starter copy of the auth-service schemas, written in the same shape that
 * openapi-typescript produces. `npm run gen:api` overwrites this file with the
 * full generated version from http://127.0.0.1:8001/openapi.json.
 */
export type paths = Record<string, never>;
export type webhooks = Record<string, never>;
export interface components {
  schemas: {
    ChangePasswordRequest: { current_password: string; new_password: string };
    ForgotPasswordRequest: { email: string };
    HTTPValidationError: { detail?: components["schemas"]["ValidationError"][] };
    LoginRequest: { email: string; password: string };
    MessageResponse: { message: string };
    PasswordReset: { new_password: string };
    ResetPasswordRequest: { email: string; code: string; new_password: string };
    RoleName: "admin" | "reviewer";
    TokenResponse: { access_token: string; token_type: string; expires_in: number };
    UserCreate: {
      name: string;
      email: string;
      password: string;
      role: components["schemas"]["RoleName"];
    };
    UserPage: {
      items: components["schemas"]["UserRead"][];
      total: number;
      page: number;
      size: number;
    };
    UserRead: {
      id: string;
      name: string;
      email: string;
      role: string;
      is_active: boolean;
      last_login_at: string | null;
      created_at: string;
    };
    UserUpdate: {
      name?: string | null;
      role?: components["schemas"]["RoleName"] | null;
      is_active?: boolean | null;
    };
    ValidationError: {
      loc: (string | number)[];
      msg: string;
      type: string;
      input?: unknown;
      ctx?: Record<string, never>;
    };
  };
  responses: never;
  parameters: never;
  requestBodies: never;
  headers: never;
  pathItems: never;
}
export type $defs = Record<string, never>;
export type operations = Record<string, never>;
