import { cleanParams, http } from "@/lib/axios";
import {
  ReprocessRunReadSchema,
  SubmissionPageSchema,
  SubmissionReadSchema,
  SubmissionTimelineSchema,
  type SubmissionListParams,
} from "../types/submission";
import { z } from "zod";
import { checked } from "@/services/response";

export const submissionService = {
  listSubmissions: (params: SubmissionListParams) =>
    checked(SubmissionPageSchema, http.get("/api/submissions", { params: cleanParams(params) })),
  getSubmission: (id: string) => checked(SubmissionReadSchema, http.get(`/api/submissions/${id}`)),
  getTimeline: (id: string) =>
    checked(SubmissionTimelineSchema, http.get(`/api/submissions/${id}/timeline`)),
  /**
   * confirmApproved: send after a 409 `confirmation_required` to replace approved timesheets.
   * refetch: true = read the attachments again from the original email in the mailbox;
   * left out = the server fetches only when the saved text is not enough.
   */
  reprocess: (
    id: string,
    reason: string,
    documentId?: string | null,
    confirmApproved = false,
    refetch = false,
  ) =>
    checked(
      ReprocessRunReadSchema,
      http.post(`/api/submissions/${id}/reprocess`, {
        reason,
        document_id: documentId || null,
        confirm_approved: confirmApproved,
        ...(refetch ? { refetch: true } : {}),
      }),
    ),
  reprocessRuns: (id: string) =>
    checked(z.array(ReprocessRunReadSchema), http.get(`/api/submissions/${id}/reprocess-runs`)),
};
