export type CompanySearch = { tab?: "details" | "senders" };

/** The company page's ?tab= (details is the default). */
export const validateCompanySearch = (s: Record<string, unknown>): CompanySearch => ({
  tab: s.tab === "senders" ? "senders" : undefined,
});
