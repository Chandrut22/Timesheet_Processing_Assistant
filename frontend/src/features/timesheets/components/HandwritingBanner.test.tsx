// @vitest-environment jsdom
// The reminder on a timesheet that came from a photo / scan read by the vision model.
import fixtures from "@/test/fixtures/api-responses.json";
import { renderWithClient } from "@/test/render";
import { cleanup, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TimesheetRead } from "../types/timesheet";

const getSubmission = vi.hoisted(() => vi.fn());
vi.mock("@/features/submissions/services/submissionService", () => ({
  submissionService: { getSubmission },
}));

const { HandwritingBanner } = await import("./HandwritingBanner");

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
  return renderWithClient(<HandwritingBanner t={timesheet} />);
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
