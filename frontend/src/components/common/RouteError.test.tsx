// @vitest-environment jsdom
import userEvent from "@testing-library/user-event";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RouteError } from "./RouteError";

afterEach(cleanup);

describe("RouteError", () => {
  it("offers a reload when the page's code is gone after a deploy", async () => {
    const reload = vi.fn();
    const onRetry = vi.fn();
    render(
      <RouteError
        error={new TypeError("Failed to fetch dynamically imported module: /assets/x.js")}
        onRetry={onRetry}
        reload={reload}
      />,
    );
    expect(screen.getByText("A new version of the app is available.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /reload/i }));
    expect(reload).toHaveBeenCalledOnce();
    expect(onRetry).not.toHaveBeenCalled();
  });

  it("shows any other error with Try again", async () => {
    const onRetry = vi.fn();
    render(<RouteError error={new Error("Not found.")} onRetry={onRetry} reload={vi.fn()} />);
    expect(screen.getByText("Not found.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
