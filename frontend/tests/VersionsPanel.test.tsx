// @vitest-environment jsdom
// The timesheet's Versions panel: the list, one version's days, and a rollback.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import fixtures from "./fixtures/api-responses.json";
import type { TimesheetRead } from "../src/api/models";

const listVersions = vi.hoisted(() => vi.fn());
const getVersion = vi.hoisted(() => vi.fn());
const restoreVersion = vi.hoisted(() => vi.fn());
vi.mock("../src/api/core", () => ({ coreApi: { listVersions, getVersion, restoreVersion } }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const { VersionsPanel } = await import("../src/features/timesheet/VersionsPanel");

const timesheet = { ...(fixtures.core.timesheet as TimesheetRead), version: 2 };

function renderPanel(readOnly = false) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <VersionsPanel t={timesheet} readOnly={readOnly} />
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  listVersions.mockReset().mockResolvedValue(fixtures.core.timesheetVersions);
  getVersion.mockReset().mockResolvedValue(fixtures.core.timesheetVersion);
  restoreVersion.mockReset().mockResolvedValue({ ...timesheet, version: 3 });
});
afterEach(cleanup);

describe("VersionsPanel", () => {
  it("lists the versions, newest first, with what replaced each one", async () => {
    renderPanel();
    const items = await screen.findAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText("Version 2")).toBeTruthy();
    expect(within(items[0]).getByText("Current")).toBeTruthy();
    expect(within(items[0]).queryByRole("button", { name: /Restore/ })).toBeNull();
    expect(within(items[1]).getByText(/Replaced by version 2/)).toBeTruthy();
    expect(within(items[1]).getByText("Days edited")).toBeTruthy();
    expect(within(items[1]).getByText(/by Rita Reviewer/)).toBeTruthy();
  });

  it("shows the days of an earlier version", async () => {
    const user = renderPanel();
    const [, old] = await screen.findAllByRole("listitem");
    await user.click(within(old).getByRole("button", { name: "View" }));
    expect(getVersion).toHaveBeenCalledWith(timesheet.id, 1);
    expect(await within(old).findByText("late shift")).toBeTruthy();
    expect(within(old).getByText(/10\.5/)).toBeTruthy();
  });

  it("restores a version with a reason", async () => {
    const user = renderPanel();
    const [, old] = await screen.findAllByRole("listitem");
    await user.click(within(old).getByRole("button", { name: /Restore/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/come back as version 3/)).toBeTruthy();
    await user.type(within(dialog).getByLabelText(/Reason/), "wrong edit");
    await user.click(within(dialog).getByRole("button", { name: "Restore version 1" }));
    expect(restoreVersion).toHaveBeenCalledWith(timesheet.id, 1, "wrong edit");
  });

  it("offers no rollback when the timesheet is read-only (exported)", async () => {
    renderPanel(true);
    await screen.findAllByRole("listitem");
    expect(screen.queryByRole("button", { name: /Restore/ })).toBeNull();
  });

  it("says when there is no earlier version", async () => {
    listVersions.mockResolvedValue([fixtures.core.timesheetVersions[0]]);
    renderPanel();
    expect(await screen.findByText(/No earlier versions/)).toBeTruthy();
  });
});
