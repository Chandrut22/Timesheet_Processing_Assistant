export type ResetSearch = { email?: string };

/** The email to fill in on the reset page (?email=, from the forgot-password page). */
export const validateResetPasswordSearch = (search: Record<string, unknown>): ResetSearch => ({
  email: typeof search.email === "string" ? search.email : undefined,
});
