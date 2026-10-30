import { createFileRoute } from "@tanstack/react-router";
import { SubmissionsPage } from "@/features/submissions/components/SubmissionsPage";
import { validateSubmissionsSearch } from "@/features/submissions/utils/submissionsSearch";

export const Route = createFileRoute("/_app/submissions/")({
  validateSearch: validateSubmissionsSearch,
  component: SubmissionsPage,
});
