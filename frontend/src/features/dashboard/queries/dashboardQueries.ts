/** Query key of the dashboard snapshot (counts and latest submissions). */
export const dashboardKeys = {
  snapshot: () => ["dashboard"] as const,
};

/** Query keys of the email listener's status and of one "Check mail now" request. */
export const mailboxKeys = {
  status: () => ["mailbox", "status"] as const,
  check: (requestId: string) => ["mailbox", "check", requestId] as const,
};
