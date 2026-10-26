import { createFileRoute } from "@tanstack/react-router";
import { ReviewQueuePage, parseReviewSearch } from "@/features/review";

export const Route = createFileRoute("/_app/review")({
  validateSearch: parseReviewSearch,
  component: ReviewQueuePage,
});
