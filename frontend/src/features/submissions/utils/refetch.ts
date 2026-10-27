import type { DocumentRead, SubmissionRead } from "../types/submission";

/** What the server records for an ignored email's attachments (never read). */
export const IGNORED_NOT_READ = "Not read: the email was ignored.";

/** A timeline step's name for people. */
export function stepLabel(step: string): string | null {
  return step === "fetch" ? "Fetch from mailbox" : null;
}

/** The file is gone and only the original email can give it back. */
function missing(d: Pick<DocumentRead, "status" | "error" | "filename">): boolean {
  return d.filename !== "email-body.txt" && (d.status === "failed" || d.error === IGNORED_NOT_READ);
}

/**
 * Will this reprocess fetch the email from the mailbox by itself? Yes when the email was
 * ignored or a file in scope failed (its text was never saved and the file is gone),
 * and the server can fetch it (refetch_blocked is null).
 */
export function fetchesFromMailbox(
  s: Pick<SubmissionRead, "source" | "status" | "documents" | "refetch_blocked">,
  documentId: string | null,
): boolean {
  if (s.source !== "email" || s.refetch_blocked) return false;
  if (s.status === "ignored") return true;
  const scope = documentId ? s.documents.filter((d) => d.id === documentId) : s.documents;
  return scope.some(missing);
}

/** The "read again from the original email" choice is offered (emails the server can fetch). */
export function canFetchFromMailbox(
  s: Pick<SubmissionRead, "source" | "refetch_blocked">,
): boolean {
  return s.source === "email" && s.refetch_blocked == null;
}
