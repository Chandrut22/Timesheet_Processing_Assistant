import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { timesheetKeys, timesheetService } from "@/features/timesheets";

type TimesheetPage = Awaited<ReturnType<typeof timesheetService.listTimesheets>>;

interface SubmissionTimesheetParams {
  submission_id: string;
  size: number;
  sort: "employee";
  order: "asc";
}

export function useSubmissionTimesheets(
  submissionId: string,
  busy: boolean,
): UseQueryResult<TimesheetPage> {
  const params: SubmissionTimesheetParams = {
    submission_id: submissionId,
    size: 100,
    sort: "employee",
    order: "asc",
  };

  return useQuery({
    queryKey: timesheetKeys.list(params),
    queryFn: () => timesheetService.listTimesheets(params),
    refetchInterval: busy ? 3000 : false,
  });
}
