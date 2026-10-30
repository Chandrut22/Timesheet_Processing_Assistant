import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { useState } from "react";

import {
  IN_PROGRESS_STATES,
  submissionKeys,
  submissionService,
  type SubmissionListParams,
} from "@/features/submissions";
import type { MutationCallbacks } from "@/hooks/mutationOptions";

import { uploadService } from "../services/uploadService";

const RECENT_UPLOADS: SubmissionListParams = { source: "upload", page: 1, size: 5 };
const POLL_MS = 5000;

type SubmissionPage = Awaited<ReturnType<typeof submissionService.listSubmissions>>;
type UploadedSubmission = Awaited<ReturnType<typeof uploadService.upload>>;

/** The latest 5 uploads (from everyone). Refreshes every 5 s while one of them is still
 * being processed, and not at all while the browser tab is hidden. */
export function useRecentUploads(): UseQueryResult<SubmissionPage> {
  return useQuery({
    queryKey: submissionKeys.recentUploads(RECENT_UPLOADS),
    queryFn: () => submissionService.listSubmissions(RECENT_UPLOADS),
    refetchInterval: (q) =>
      q.state.data?.items.some((s) => IN_PROGRESS_STATES.has(s.state)) ? POLL_MS : false,
    refetchIntervalInBackground: false,
  });
}

export type UploadVariables = { files: File[]; companyId?: string };

export type Upload = {
  upload: UseMutationResult<UploadedSubmission, Error, UploadVariables>;
  /** 0-100 while the files are being sent; null otherwise. */
  progress: number | null;
};

/** Send the files as one submission. The page shows the error itself. */
export function useUpload(
  opts: MutationCallbacks<UploadedSubmission, UploadVariables> = {},
): Upload {
  const queryClient = useQueryClient();
  const [progress, setProgress] = useState<number | null>(null);
  const upload = useMutation({
    mutationFn: ({ files, companyId }: UploadVariables) =>
      uploadService.upload(files, companyId, setProgress),
    meta: { silentError: true },
    onSuccess: (submission, v) => {
      void queryClient.invalidateQueries({ queryKey: submissionKeys.all });
      opts.onSuccess?.(submission, v);
    },
    onSettled: () => setProgress(null),
  });
  return { upload, progress };
}
