// @vitest-environment jsdom
// The reminder on a timesheet that came from a photo / scan read by the vision model.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import fixtures from "./fixtures/api-responses.json";
import type { TimesheetRead } from "../src/api/models";

const getSubmission = vi.hoisted(() => vi.fn());
vi.mock("../src/api/core", () => ({ coreApi: { getSubmission } }));

const { HandwritingBanner } = await import("../src/features/timesheet/HandwritingBanner");

const submission = fixtures.core.submissionPage.items[0];
const timesheet = {
  ...(fixtures.core.timesheet as TimesheetRead),
  submission_id: submission.id,
  document_id: submission.documents[0].id,
};

function withDocument(extra: Record<string, unknown>) {
  getSubmission.mockResolvedValue({
    ...submission,
    documents: [{ ...submission.documents[0], ...extra }],
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <HandwritingBanner t={timesheet} />
    </QueryClientProvider>,
  );
}

beforeEach(() => getSubmission.mockReset());
afterEach(cleanup);

describe("HandwritingBanner", () => {
  it("asks to check handwritten hours against the original", async () => {
    withDocument({
      read_method: "vision",
      writing_class: "mixed",
      has_handwritten_hours: true,
      unclear_marks: 1,
    });
    expect(await screen.findByText(/Hours were written by hand/)).toBeTruthy();
    expect(screen.getByText(/1 value was unreadable and left out/)).toBeTruthy();
  });

  it("warns when the page was hard to read", async () => {
    withDocument({ read_method: "vision", writing_class: "uncertain" });
    expect(await screen.findByText(/hard to read/)).toBeTruthy();
  });

  it("says nothing for a printed scan or a typed document", async () => {
    const printed = withDocument({ read_method: "vision", writing_class: "printed_only" });
    await vi.waitFor(() => expect(getSubmission).toHaveBeenCalled());
    expect(printed.container.textContent).toBe("");
    cleanup();
    const typed = withDocument({ read_method: "docling" });
    await vi.waitFor(() => expect(getSubmission).toHaveBeenCalledTimes(2));
    expect(typed.container.textContent).toBe("");
  });
});
