import {
  SUBMISSION_STATES,
  SUBMISSION_STATUSES,
  type SubmissionSource,
  type SubmissionState,
  type SubmissionStatus,
} from "../types/submission";

export type SubmissionsSearch = {
  status?: SubmissionStatus;
  state?: SubmissionState;
  source?: SubmissionSource;
  company_id?: string;
  page?: number;
};

/** The emails and uploads list's filters and page in the URL. Anything unknown is dropped. */
export const validateSubmissionsSearch = (s: Record<string, unknown>): SubmissionsSearch => ({
  status: (SUBMISSION_STATUSES as string[]).includes(String(s.status))
    ? (s.status as SubmissionStatus)
    : undefined,
  state: (SUBMISSION_STATES as string[]).includes(String(s.state))
    ? (s.state as SubmissionState)
    : undefined,
  source: s.source === "email" || s.source === "upload" ? s.source : undefined,
  company_id: typeof s.company_id === "string" && s.company_id ? s.company_id : undefined,
  page: Number.isInteger(Number(s.page)) && Number(s.page) > 1 ? Number(s.page) : undefined,
});
