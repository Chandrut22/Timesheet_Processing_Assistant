// @vitest-environment jsdom
// "Recent uploads": loading / empty / error / data, and polling only while something is
// still being processed (never while the tab is hidden).
import { QueryClient, QueryClientProvider, focusManager } from "@tanstack/react-query";
import { act, cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Page } from "@/types/api";
import type { SubmissionRead } from "@/features/submissions/types/submission";

const list = vi.hoisted(() => vi.fn<() => Promise<Page<SubmissionRead>>>());
vi.mock("@/features/submissions/services/submissionService", () => ({
  submissionService: { listSubmissions: list },
}));
vi.mock("@/features/companies/hooks/useCompanies", () => ({
  useCompanies: () => ({ data: [], isLoading: false }),
  useCompanyMap: () => new Map([["c1", { id: "c1", name: "Lakeside Logistics" }]]),
}));
vi.mock("@tanstack/react-router", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-router")>()),
  Link: ({ children, to }: { children: ReactNode; to: string }) => <a href={to}>{children}</a>,
}));

const { RecentUploads } = await import("./RecentUploads");

function submission(over: Partial<SubmissionRead>): SubmissionRead {
  return {
    id: "s1",
    source: "upload",
    status: "processed",
    state: "awaiting_review",
    state_reason: null,
    company_id: "c1",
    sender_email: null,
    subject: null,
    uploaded_by_id: "u1",
    uploaded_by_name: "Rita Reviewer",
    received_at: new Date().toISOString(),
    processed_at: null,
    error: null,
    attempts: 1,
    retry_at: null,
    documents: [
      {
        id: "d1",
        filename: "week-1.pdf",
        content_type: "application/pdf",
        size_bytes: 10,
        sha256: "x",
        status: "parsed",
        error: null,
        read_limit: null,
        unclear_marks: 0,
        has_handwritten_hours: false,
        skipped_by_classifier: false,
        created_at: new Date().toISOString(),
      },
      {
        id: "d2",
        filename: "week-2.pdf",
        content_type: "application/pdf",
        size_bytes: 10,
        sha256: "y",
        status: "parsed",
        error: null,
        read_limit: null,
        unclear_marks: 0,
        has_handwritten_hours: false,
        skipped_by_classifier: false,
        created_at: new Date().toISOString(),
      },
    ],
    ...over,
  };
}
const page = (
  items: SubmissionRead[],
): { items: SubmissionRead[]; total: number; page: number; size: number } => ({
  items,
  total: items.length,
  page: 1,
  size: 5,
});

function renderCard(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RecentUploads />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  list.mockReset();
  vi.useFakeTimers({ shouldAdvanceTime: true });
});
afterEach(() => {
  cleanup();
  focusManager.setFocused(undefined);
  vi.useRealTimers();
});

describe("RecentUploads", () => {
  it("shows a skeleton while loading", () => {
    list.mockReturnValue(new Promise(() => undefined));
    renderCard();
    expect(screen.getByLabelText("Loading recent uploads")).toBeTruthy();
  });

  it("shows the empty state", async () => {
    list.mockResolvedValue(page([]));
    renderCard();
    expect(await screen.findByText("No uploads yet. Files you upload appear here.")).toBeTruthy();
  });

  it("shows an error with Retry", async () => {
    list.mockRejectedValueOnce(new Error("Can't reach the server."));
    list.mockResolvedValue(page([]));
    renderCard();
    const retry = await screen.findByRole("button", { name: /Try again/ });
    await act(async () => retry.click());
    expect(await screen.findByText(/No uploads yet/)).toBeTruthy();
  });

  it("lists uploads: first file +N more, company, who and when, state", async () => {
    list.mockResolvedValue(
      page([submission({}), submission({ id: "s2", company_id: null, documents: [] })]),
    );
    renderCard();
    const first = await screen.findByText("week-1.pdf +1 more");
    expect(first.getAttribute("title")).toBe("week-1.pdf\nweek-2.pdf");
    expect(screen.getByText("Lakeside Logistics")).toBeTruthy();
    expect(screen.getByText("Company not set")).toBeTruthy();
    expect(screen.getAllByText(/^Uploaded by Rita Reviewer · /)).toHaveLength(2);
    expect(screen.getAllByText("Awaiting review")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "View all" }).getAttribute("href")).toBe(
      "/submissions",
    );
  });

  it("polls every 5 s only while an upload is in progress", async () => {
    list.mockResolvedValue(page([submission({ state: "reading" })]));
    renderCard();
    await screen.findByText("week-1.pdf +1 more");
    expect(list).toHaveBeenCalledTimes(1);
    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(list).toHaveBeenCalledTimes(2);

    list.mockResolvedValue(page([submission({ state: "awaiting_review" })]));
    await act(() => vi.advanceTimersByTimeAsync(5000)); // this answer is no longer in progress
    const calls = list.mock.calls.length;
    await act(() => vi.advanceTimersByTimeAsync(20000));
    expect(list).toHaveBeenCalledTimes(calls); // stopped
  });

  it("does not poll while the tab is hidden", async () => {
    list.mockResolvedValue(page([submission({ state: "matching" })]));
    renderCard();
    await screen.findByText("week-1.pdf +1 more");
    act(() => focusManager.setFocused(false));
    const calls = list.mock.calls.length;
    await act(() => vi.advanceTimersByTimeAsync(20000));
    expect(list).toHaveBeenCalledTimes(calls);
  });
});
