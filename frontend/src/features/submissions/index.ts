// Public API of the submissions feature: other parts of the app import only from here.
// Pages are not exported: only their route files import them (src/routes), so each
// page stays in its own chunk (autoCodeSplitting).
export { SourceIcon, SubmissionStateBadge } from "./components/SubmissionBadges";
export { submissionKeys } from "./queries/submissionQueries";
export { submissionService } from "./services/submissionService";
export {
  DocumentReadSchema,
  ProcessingStepReadSchema,
  ReprocessRunReadSchema,
  StateChangeReadSchema,
  SubmissionPageSchema,
  SubmissionReadSchema,
  SubmissionSourceSchema,
  SubmissionStateSchema,
  SubmissionStatusSchema,
  SubmissionTimelineSchema,
  WritingClassSchema,
} from "./types/submission";
export type {
  SubmissionListParams,
  SubmissionRead,
  SubmissionSource,
  SubmissionState,
  SubmissionStatus,
} from "./types/submission";
export { IN_PROGRESS_STATES } from "./utils/submissionStates";
export { hasHandwrittenHours, writingChip } from "./utils/writing";
export { isSubmissionBusy, useSubmissionTimeline } from "./hooks/useSubmissionTimeline";

export { useSubmissionTimesheets } from "./hooks/useSubmissionTimesheets";
export { useSubmission, useSubmissionsList } from "./hooks/useSubmissions";
