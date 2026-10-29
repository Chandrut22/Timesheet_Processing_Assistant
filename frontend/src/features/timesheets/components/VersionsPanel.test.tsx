// @vitest-environment jsdom
// The timesheet's Versions panel: the list, one version's days, and a rollback.
import userEvent from "@testing-library/user-event";
import fixtures from "@/test/fixtures/api-responses.json";
import { renderWithClient } from "@/test/render";
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TimesheetRead } from "../types/timesheet";
import type { UserEvent } from "@testing-library/user-event";

const listVersions = vi.hoisted(() => vi.fn());
const getVersion = vi.hoisted(() => vi.fn());
const restoreVersion = vi.hoisted(() => vi.fn());
vi.mock("../services/timesheetService", () => ({
  timesheetService: { listVersions, getVersion, restoreVersion },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const { VersionsPanel } = await import("./VersionsPanel");

const timesheet = { ...(fixtures.core.timesheet as TimesheetRead), version: 2 };

function renderPanel(readOnly = false): UserEvent {
  renderWithClient(<VersionsPanel t={timesheet} readOnly={readOnly} />);
  return userEvent.setup();
}

beforeEach(() => {
  listVersions.mockReset().mockResolvedValue(fixtures.core.timesheetVersions);
  getVersion.mockReset().mockResolvedValue(fixtures.core.timesheetVersion);
  restoreVersion.mockReset().mockResolvedValue({ ...timesheet, version: 1 });
});
afterEach(cleanup);

describe("VersionsPanel", () => {
  it("lists the versions, highest first, with what happened next", async () => {
    renderPanel();
    const items = await screen.findAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText("Version 2")).toBeTruthy();
    expect(within(items[0]).getByText("Current")).toBeTruthy();
    expect(within(items[0]).queryByRole("button", { name: /Restore/ })).toBeNull();
    expect(within(items[1]).getByText(/Then:/)).toBeTruthy();
    expect(within(items[1]).getByText("Days edited as a new version")).toBeTruthy();
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
    expect(within(dialog).getByText(/becomes version 1 again/)).toBeTruthy();
    expect(within(dialog).getByText(/No new version is made/)).toBeTruthy();
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
