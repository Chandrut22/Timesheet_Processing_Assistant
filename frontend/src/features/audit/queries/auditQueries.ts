/** Query keys for the audit history of one timesheet or submission. */
export const auditKeys = {
  entity: (type: "timesheet" | "submission", id: string) => ["audit", type, id] as const,
};
