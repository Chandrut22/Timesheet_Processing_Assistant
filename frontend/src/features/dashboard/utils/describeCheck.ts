import type { MailboxCheck } from "../types/mailbox";

/** "3 new emails: 2 queued for processing, 1 ignored." (or "No new email."). */
export function describeCheck(check: MailboxCheck): string {
  const found = check.found ?? 0;
  if (!found) return "No new email.";
  const parts = [`${check.queued ?? 0} queued for processing`];
  if (check.ignored) parts.push(`${check.ignored} ignored`);
  if (check.duplicates) parts.push(`${check.duplicates} already received`);
  if (check.failed) parts.push(`${check.failed} could not be saved`);
  return `${found} new email${found === 1 ? "" : "s"}: ${parts.join(", ")}.`;
}
