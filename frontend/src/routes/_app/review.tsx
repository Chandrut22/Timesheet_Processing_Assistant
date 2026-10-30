import { createFileRoute } from "@tanstack/react-router";
import { ReviewQueuePage } from "@/features/review/components/ReviewPage";
import { parseReviewSearch } from "@/features/review/utils/search";

export const Route = createFileRoute("/_app/review")({
  validateSearch: parseReviewSearch,
  component: ReviewQueuePage,
});
