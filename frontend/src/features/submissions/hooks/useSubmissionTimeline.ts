import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import type { SubmissionRead } from "../types/submission";
import { submissionService } from "../services/submissionService";
import { submissionKeys } from "../queries/submissionQueries";

function isBusy(submission: SubmissionRead): boolean {
  const inProgressStates = new Set([
    "received",
    "reading",
    "matching",
    "rule_checks",
    "reprocessing",
  ]);

  return (
    submission.status === "received" ||
    submission.status === "processing" ||
    inProgressStates.has(submission.state)
  );
}

type SubmissionTimelineData = Awaited<
  ReturnType<typeof submissionService.getTimeline>
>;

export function isSubmissionBusy(submission: SubmissionRead): boolean {
  return isBusy(submission);
}

export function useSubmissionTimeline(
  submissionId: string,
): UseQueryResult<SubmissionTimelineData, Error> {
  return useQuery({
    queryKey: submissionKeys.timeline(submissionId),
    queryFn: () => submissionService.getTimeline(submissionId),
    refetchInterval: (query) =>
      query.state.data && isBusy(query.state.data.submission) ? 3000 : false,
  });
}