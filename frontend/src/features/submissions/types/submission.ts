import { z } from "zod";
import { int, isoDateTime, jsonObject, pageOf, uuid } from "@/services/schemas";
import { AuditEventReadSchema } from "@/features/audit";

export const SubmissionStatusSchema = z.enum([
  "received",
  "processing",
  "processed",
  "failed",
  "ignored",
]);

export const SubmissionStateSchema = z.enum([
  "received",
  "reading",
  "matching",
  "rule_checks",
  "awaiting_review",
  "approved",
  "rejected",
  "exported",
  "ignored",
  "failed",
  "reprocessing",
]);

export const SubmissionSourceSchema = z.enum(["email", "upload"]);

/** How a photo / scan is written, as the vision model saw it. */
export const WritingClassSchema = z.enum([
  "printed_only",
  "handwritten_only",
  "mixed",
  "no_text",
  "uncertain",
]);

export const DocumentReadSchema = z.object({
  id: uuid,
  filename: z.string(),
  content_type: z.string(),
  size_bytes: int,
  sha256: z.string(),
  status: z.string(),
  error: z.string().nullable(),
  /** How much of a large file was read (pages / sheets); null when all of it was. */
  read_limit: z.union([jsonObject, z.string()]).nullish(),
  /** docling (typed / OCR), plain (CSV, TXT) or vision (photo / scan read by an AI model). */
  read_method: z.enum(["docling", "plain", "vision"]).nullish(),
  /** How many [UNCLEAR] marks the vision model left; 0 otherwise. */
  unclear_marks: int.nonnegative().default(0),
  /** Photos / scans only: how the page is written (null for typed documents). */
  writing_class: WritingClassSchema.nullish(),
  writing_confidence: z.number().min(0).max(1).nullish(),
  has_handwritten_hours: z.boolean().default(false),
  writing_reason: z.string().nullish(),
  created_at: isoDateTime,
});

export const SubmissionReadSchema = z.object({
  id: uuid,
  source: z.string(),
  status: z.string(),
  state: z.string(),
  state_reason: z.string().nullable(),
  company_id: uuid.nullable(),
  sender_email: z.string().nullable(),
  subject: z.string().nullable(),
  uploaded_by_id: uuid.nullable(),
  uploaded_by_name: z.string().nullable(),
  received_at: isoDateTime,
  processed_at: isoDateTime.nullable(),
  error: z.string().nullable(),
  attempts: int,
  retry_at: isoDateTime.nullable(),
  documents: z.array(DocumentReadSchema),
  // Opens the original email in the mailbox (Gmail); null for uploads or when links
  // are turned off (MAILBOX_ACCOUNT not set). Optional: older servers do not send it.
  mail_url: z.string().url().nullish(),
});

export const SubmissionPageSchema = pageOf(SubmissionReadSchema);

export const StateChangeReadSchema = z.object({
  id: uuid,
  from_state: z.string().nullable(),
  to_state: z.string(),
  reason: z.string().nullable(),
  actor_name: z.string().nullable(),
  created_at: isoDateTime,
});

export const ProcessingStepReadSchema = z.object({
  id: uuid,
  step: z.string(),
  result: z.string(),
  message: z.string(),
  document_id: uuid.nullable(),
  timesheet_id: uuid.nullable(),
  input: jsonObject,
  output: jsonObject,
  error_details: z.string().nullable(),
  duration_ms: int,
  reprocess_run_id: uuid.nullable(),
  trace_id: z.string().nullish(),
  created_at: isoDateTime,
});

export const ReprocessRunReadSchema = z.object({
  id: uuid,
  submission_id: uuid,
  document_id: uuid.nullable(),
  reason: z.string(),
  requested_by_name: z.string(),
  status: z.string(),
  before_result: jsonObject,
  after_result: jsonObject.nullable(),
  error: z.string().nullable(),
  created_at: isoDateTime,
  completed_at: isoDateTime.nullable(),
});

export const SubmissionTimelineSchema = z.object({
  submission: SubmissionReadSchema,
  states: z.array(StateChangeReadSchema),
  steps: z.array(ProcessingStepReadSchema),
  audit: z.array(AuditEventReadSchema),
  reprocess_runs: z.array(ReprocessRunReadSchema),
});

export type SubmissionStatus = z.infer<typeof SubmissionStatusSchema>;

export type SubmissionState = z.infer<typeof SubmissionStateSchema>;

export type SubmissionSource = z.infer<typeof SubmissionSourceSchema>;

export type DocumentRead = z.infer<typeof DocumentReadSchema>;

export type WritingClass = z.infer<typeof WritingClassSchema>;

export type SubmissionRead = z.infer<typeof SubmissionReadSchema>;

export type StateChangeRead = z.infer<typeof StateChangeReadSchema>;

export type ProcessingStepRead = z.infer<typeof ProcessingStepReadSchema>;

export type ReprocessRunRead = z.infer<typeof ReprocessRunReadSchema>;

export type SubmissionTimeline = z.infer<typeof SubmissionTimelineSchema>;

export const SUBMISSION_STATUSES: SubmissionStatus[] = [
  "received",
  "processing",
  "processed",
  "failed",
  "ignored",
];

export const SUBMISSION_STATES: SubmissionState[] = [
  "received",
  "reading",
  "matching",
  "rule_checks",
  "awaiting_review",
  "approved",
  "rejected",
  "exported",
  "ignored",
  "failed",
  "reprocessing",
];

export type SubmissionListParams = {
  status?: SubmissionStatus;
  state?: SubmissionState;
  source?: SubmissionSource;
  company_id?: string;
  page?: number;
  size?: number;
};
