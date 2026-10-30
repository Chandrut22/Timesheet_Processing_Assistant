import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";

import { submissionKeys } from "../queries/submissionQueries";
import { submissionService } from "../services/submissionService";
import type { SubmissionListParams, SubmissionRead } from "../types/submission";

type SubmissionPage = Awaited<ReturnType<typeof submissionService.listSubmissions>>;

/** The emails and uploads list. Refreshes every 5 s while one on screen is still being
 * processed. */
export function useSubmissionsList(params: SubmissionListParams): UseQueryResult<SubmissionPage> {
  return useQuery({
    queryKey: submissionKeys.list(params),
    queryFn: () => submissionService.listSubmissions(params),
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      query.state.data?.items.some((s) => s.status === "received" || s.status === "processing")
        ? 5000
        : false,
  });
}

/** One email or upload with its documents (shared by every panel that shows it). */
export function useSubmission(submissionId: string): UseQueryResult<SubmissionRead> {
  return useQuery({
    queryKey: submissionKeys.detail(submissionId),
    queryFn: () => submissionService.getSubmission(submissionId),
  });
}
