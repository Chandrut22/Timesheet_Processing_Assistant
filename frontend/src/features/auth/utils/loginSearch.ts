export type LoginSearch = { redirect?: string };

/** Where to go after signing in (?redirect=). Never back to /login, and never very long. */
export const validateLoginSearch = (search: Record<string, unknown>): LoginSearch => {
  const r = search.redirect;
  return {
    redirect: typeof r === "string" && r.length <= 1000 && !r.startsWith("/login") ? r : undefined,
  };
};
