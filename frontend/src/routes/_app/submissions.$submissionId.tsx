import { createFileRoute } from "@tanstack/react-router";
import { SubmissionPage } from "@/features/submissions/components/SubmissionPage";

export const Route = createFileRoute("/_app/submissions/$submissionId")({
  component: SubmissionPage,
});
