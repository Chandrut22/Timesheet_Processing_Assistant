import { createFileRoute } from "@tanstack/react-router";
import { SubmissionsPage, validateSubmissionsSearch } from "@/features/submissions";

export const Route = createFileRoute("/_app/submissions/")({
  validateSearch: validateSubmissionsSearch,
  component: SubmissionsPage,
});
