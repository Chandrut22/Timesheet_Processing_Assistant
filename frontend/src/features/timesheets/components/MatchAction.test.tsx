// @vitest-environment jsdom
// The match button (review queue, submission page): "Match" for an unmatched row, "Change" for a matched
// one, nothing once exported.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MatchAction } from "./MatchAction";

afterEach(cleanup);

describe("MatchAction", () => {
  it("offers Match on an unmatched row", () => {
    const onMatch = vi.fn();
    render(
      <MatchAction
        t={{ employee_id: null, status: "needs_review" }}
        name="Jon Smth"
        onMatch={onMatch}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Match employee for «Jon Smth»" }));
    expect(onMatch).toHaveBeenCalledOnce();
  });

  it("offers Change on a matched row", () => {
    const onMatch = vi.fn();
    render(
      <MatchAction
        t={{ employee_id: "e1", status: "approved" }}
        name="John Smith"
        onMatch={onMatch}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Change employee (now John Smith)" }));
    expect(onMatch).toHaveBeenCalledOnce();
  });

  it("shows nothing while disabled (submission still processing)", () => {
    const { container } = render(
      <MatchAction
        t={{ employee_id: null, status: "needs_review" }}
        name="Jon"
        onMatch={vi.fn()}
        disabled
      />,
    );
    expect(container.textContent).toBe("");
  });

  it("asks to confirm a close-spelling match", () => {
    const onMatch = vi.fn();
    render(
      <MatchAction
        t={{ employee_id: "e1", status: "needs_review", match_method: "fuzzy" }}
        name="John Smith"
        onMatch={onMatch}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm employee (close spelling: John Smith)" }),
    );
    expect(onMatch).toHaveBeenCalledOnce();
  });

  it("shows nothing for an exported timesheet", () => {
    const { container } = render(
      <MatchAction t={{ employee_id: null, status: "exported" }} name="Jon" onMatch={vi.fn()} />,
    );
    expect(container.textContent).toBe("");
  });
});
