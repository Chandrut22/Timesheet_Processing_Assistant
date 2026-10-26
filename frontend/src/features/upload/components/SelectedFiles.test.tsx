// @vitest-environment jsdom
import userEvent from "@testing-library/user-event";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SelectedFiles } from "./SelectedFiles";

const files = [new File(["a".repeat(2048)], "week-1.pdf"), new File(["b"], "hours.csv")];
afterEach(cleanup);

describe("SelectedFiles", () => {
  it("lists the files with a total, and removes one", async () => {
    const onRemove = vi.fn();
    const user = userEvent.setup();
    render(<SelectedFiles files={files} onRemove={onRemove} onClear={() => undefined} />);
    expect(screen.getByText(/^2 files · /)).toBeTruthy();
    expect(screen.getByTitle("week-1.pdf")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Remove hours.csv" }));
    expect(onRemove).toHaveBeenCalledWith(1);
  });

  it("clears all", async () => {
    const onClear = vi.fn();
    const user = userEvent.setup();
    render(<SelectedFiles files={files} onRemove={() => undefined} onClear={onClear} />);
    await user.click(screen.getByRole("button", { name: /Clear all/ }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("disables every control while uploading", () => {
    render(
      <SelectedFiles files={files} disabled onRemove={() => undefined} onClear={() => undefined} />,
    );
    for (const button of screen.getAllByRole("button")) {
      expect(button.hasAttribute("disabled")).toBe(true);
    }
  });
});
