import { getRouteApi, Link } from "@tanstack/react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { RotateCcw, Upload } from "lucide-react";
import { useMemo, type JSX } from "react";
import {
  type SubmissionListParams,
  SUBMISSION_STATES,
  SUBMISSION_STATUSES,
  type SubmissionSource,
  type SubmissionState,
  type SubmissionStatus,
} from "../types/submission";
import { SourceIcon, SubmissionStateBadge, SubmissionStatusBadge } from "./SubmissionBadges";
import { CompanySelect } from "@/features/companies";
import { MailLink } from "@/components/common/MailLink";
import { PageHeader } from "@/components/common/PageHeader";
import { Pagination } from "@/components/common/Pagination";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/common/States";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label, NativeSelect } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDateTime, formatTime, humanize } from "@/utils/format";
import { submissionService } from "../services/submissionService";
import { submissionKeys } from "../queries/submissionQueries";
import { BackButton } from "@/components/common/BackButton";

const routeApi = getRouteApi("/_app/submissions/");

type SubmissionsSearch = {
  status?: SubmissionStatus;
  state?: SubmissionState;
  source?: SubmissionSource;
  company_id?: string;
  page?: number;
};

const PAGE_SIZE = 25;

export function SubmissionsPage(): JSX.Element {
  const search = routeApi.useSearch();
  const navigate = routeApi.useNavigate();
  const params: SubmissionListParams = useMemo(
    () => ({ ...search, page: search.page ?? 1, size: PAGE_SIZE }),
    [search],
  );

  const q = useQuery({
    queryKey: submissionKeys.list(params),
    queryFn: () => submissionService.listSubmissions(params),
    placeholderData: keepPreviousData,
    // Live updates while anything on screen is still being processed.
    refetchInterval: (query) =>
      query.state.data?.items.some((s) => s.status === "received" || s.status === "processing")
        ? 5000
        : false,
  });

  const update = (patch: Partial<SubmissionsSearch>): void =>
    void navigate({
      search: (prev) => {
        const next: SubmissionsSearch = { ...prev, ...patch };
        if (!("page" in patch)) next.page = undefined;
        return next;
      },
      replace: true,
    });

  return (
    <>
      <PageHeader
        title="Submissions"
        back={<BackButton fallback="/" fallbackLabel="Dashboard" />}
        description="Every email and upload, and where it is in processing."
        actions={
          <Button asChild>
            <Link to="/upload">
              <Upload /> Upload files
            </Link>
          </Button>
        }
      />

      <Card className="mb-4 p-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <div className="grid gap-1.5">
            <Label htmlFor="s-status">Processing</Label>
            <NativeSelect
              id="s-status"
              value={search.status ?? ""}
              onChange={(e) =>
                update({ status: (e.target.value || undefined) as SubmissionStatus | undefined })
              }
            >
              <option value="">Any</option>
              {SUBMISSION_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {humanize(s)}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="s-state">State</Label>
            <NativeSelect
              id="s-state"
              value={search.state ?? ""}
              onChange={(e) =>
                update({ state: (e.target.value || undefined) as SubmissionState | undefined })
              }
            >
              <option value="">Any</option>
              {SUBMISSION_STATES.map((s) => (
                <option key={s} value={s}>
                  {humanize(s)}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="s-source">Source</Label>
            <NativeSelect
              id="s-source"
              value={search.source ?? ""}
              onChange={(e) =>
                update({ source: (e.target.value || undefined) as SubmissionSource | undefined })
              }
            >
              <option value="">Email and upload</option>
              <option value="email">Email</option>
              <option value="upload">Upload</option>
            </NativeSelect>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="s-company">Company</Label>
            <CompanySelect
              id="s-company"
              value={search.company_id ?? ""}
              onChange={(company_id) => update({ company_id: company_id || undefined })}
            />
          </div>
          <div className="flex items-end">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void navigate({ search: {}, replace: true })}
            >
              <RotateCcw /> Reset
            </Button>
          </div>
        </div>
      </Card>

      <Card>
        {q.isPending ? (
          <TableSkeleton rows={8} cols={7} />
        ) : q.isError ? (
          <div className="p-4">
            <ErrorState error={q.error} onRetry={() => void q.refetch()} />
          </div>
        ) : q.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="No submissions match"
              hint="Try other filters, or upload a timesheet."
            />
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8">
                    <span className="sr-only">Source</span>
                  </TableHead>
                  <TableHead>From</TableHead>
                  <TableHead>Subject</TableHead>
                  <TableHead>Received</TableHead>
                  <TableHead>State</TableHead>
                  <TableHead>Processing</TableHead>
                  <TableHead className="text-right">Docs</TableHead>
                  <TableHead className="text-right">Attempts</TableHead>
                  <TableHead>Problem</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {q.data.items.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell>
                      <SourceIcon source={s.source} />
                    </TableCell>
                    <TableCell className="max-w-56">
                      <Link
                        to="/submissions/$submissionId"
                        params={{ submissionId: s.id }}
                        className="block truncate font-medium hover:underline"
                      >
                        {s.sender_email ?? s.uploaded_by_name ?? "—"}
                      </Link>
                    </TableCell>
                    <TableCell className="max-w-64 truncate text-muted-foreground">
                      <MailLink url={s.mail_url}>{s.subject ?? "—"}</MailLink>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatDateTime(s.received_at)}
                    </TableCell>
                    <TableCell>
                      <SubmissionStateBadge state={s.state} />
                    </TableCell>
                    <TableCell>
                      <SubmissionStatusBadge status={s.status} />
                    </TableCell>
                    <TableCell className="tabular text-right">{s.documents.length}</TableCell>
                    <TableCell className="tabular text-right">{s.attempts}</TableCell>
                    <TableCell className="max-w-72 text-sm whitespace-normal">
                      {s.retry_at ? (
                        <span className="text-amber-700">Retrying at {formatTime(s.retry_at)}</span>
                      ) : null}
                      {s.error ? <span className="block text-red-700">{s.error}</span> : null}
                      {!s.retry_at && !s.error ? (
                        <span className="text-muted-foreground">—</span>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Pagination
              page={params.page ?? 1}
              size={PAGE_SIZE}
              total={q.data.total}
              onPage={(page) => update({ page })}
            />
          </>
        )}
      </Card>
    </>
  );
}

/** The page's search params, checked when the URL changes. */
export const validateSubmissionsSearch = (s: Record<string, unknown>): SubmissionsSearch => ({
  status: (SUBMISSION_STATUSES as string[]).includes(String(s.status))
    ? (s.status as SubmissionStatus)
    : undefined,
  state: (SUBMISSION_STATES as string[]).includes(String(s.state))
    ? (s.state as SubmissionState)
    : undefined,
  source: s.source === "email" || s.source === "upload" ? s.source : undefined,
  company_id: typeof s.company_id === "string" && s.company_id ? s.company_id : undefined,
  page: Number.isInteger(Number(s.page)) && Number(s.page) > 1 ? Number(s.page) : undefined,
});
