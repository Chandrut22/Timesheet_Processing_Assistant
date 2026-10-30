import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { holidayKeys } from "../queries/holidayQueries";
import { holidayService } from "../services/holidayService";

type HolidayListParams = Parameters<typeof holidayService.listHolidays>[0];

type HolidayListData = Awaited<ReturnType<typeof holidayService.listHolidays>>;

export function useHolidaysList(params: HolidayListParams): UseQueryResult<HolidayListData> {
  return useQuery<HolidayListData>({
    queryKey: holidayKeys.list(params),
    queryFn: () => holidayService.listHolidays(params),
  });
}
