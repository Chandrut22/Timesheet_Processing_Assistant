import type { SubmissionListParams } from "../types/submission";

/** Query keys for submissions. */
export const submissionKeys = {
  all: ["submissions"] as const,
  list: (p: SubmissionListParams) => ["submissions", "list", p] as const,
  detail: (id: string) => ["submissions", "detail", id] as const,
  timeline: (id: string) => ["submissions", "timeline", id] as const,
  /** The Upload page's "Recent uploads" card (under "submissions", so an upload refreshes it). */
  recentUploads: (p: SubmissionListParams) => ["submissions", "recent-uploads", p] as const,
};
