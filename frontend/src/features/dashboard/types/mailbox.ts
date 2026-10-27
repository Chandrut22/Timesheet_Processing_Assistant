import { z } from "zod";
import { int } from "@/services/schemas";

/** GET /api/email/status: the email listener, from its heartbeat. */
export const MailboxStatusSchema = z.object({
  /** null = the listener has never reported (not started yet). */
  enabled: z.boolean().nullable(),
  running: z.boolean(),
  connected: z.boolean(),
  mailbox: z.string().nullable(),
  last_check_at: z.string().nullable(),
  last_found: int.nullable(),
  last_queued: int.nullable(),
  last_ignored: int.nullable(),
  last_error: z.string().nullable(),
  /** Seconds until "Check mail now" can be pressed again. */
  cooldown_seconds: int,
});
export type MailboxStatus = z.infer<typeof MailboxStatusSchema>;

/** POST /api/email/check-now and GET /api/email/check-now/{id}. */
export const MailboxCheckSchema = z.object({
  request_id: z.string(),
  state: z.enum(["queued", "running", "done", "failed"]),
  requested_at: z.string().nullish(),
  requested_by: z.string().nullish(),
  started_at: z.string().nullish(),
  finished_at: z.string().nullish(),
  found: int.nullish(),
  queued: int.nullish(),
  ignored: int.nullish(),
  duplicates: int.nullish(),
  failed: int.nullish(),
  note: z.string().nullish(),
  error: z.string().nullish(),
});
export type MailboxCheck = z.infer<typeof MailboxCheckSchema>;
