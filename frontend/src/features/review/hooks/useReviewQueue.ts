import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { timesheetKeys, timesheetService } from "@/features/timesheets";
import type { ReviewSearch } from "../utils/search";
import { reviewParams } from "../utils/search";

export function useReviewQueue(search: ReviewSearch) {
  const params = reviewParams(search);

  return useQuery({
    queryKey: timesheetKeys.list(params),
    queryFn: ({ signal }) => timesheetService.listTimesheets(params, signal),
    placeholderData: keepPreviousData,
  });
}
