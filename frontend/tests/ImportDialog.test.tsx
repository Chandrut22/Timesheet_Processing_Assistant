// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ImportOptions, ImportReport } from "../src/api/models";

const api = vi.hoisted(() => ({
  importFile: vi.fn(),
  downloadTemplate: vi.fn(),
}));
vi.mock("../src/api/imports", () => ({ importApi: api }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const { ImportDialog } = await import("../src/features/import/ImportDialog");

const report = (over: Partial<ImportReport>): ImportReport => ({
  resource: "employees",
  file_name: "staff.csv",
  dry_run: true,
  committed: false,
  on_error: "abort",
  on_duplicate: "error",
  total_rows: 2,
  created: 2,
  updated: 0,
  skipped: 0,
  failed: 0,
  warnings: [],
  rows: [
    { row: 2, status: "created", errors: [], warnings: [] },
    { row: 3, status: "created", errors: [], warnings: [] },
  ],
  rows_omitted: 0,
  ...over,
});

function renderDialog(resource: "employees" | "users" = "employees") {
  const onImported = vi.fn();
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ImportDialog
        resource={resource}
        open
        onOpenChange={() => undefined}
        onImported={onImported}
      />
    </QueryClientProvider>,
  );
  return { onImported, user: userEvent.setup() };
}

const csv = () =>
  new File(["employee_code,full_name\nE1,Ann\n"], "staff.csv", { type: "text/csv" });

beforeEach(() => {
  api.importFile.mockReset();
  api.downloadTemplate.mockReset();
});
afterEach(cleanup);

describe("ImportDialog", () => {
  it("checks the file first (dry run), then imports the same file for real", async () => {
    const { user, onImported } = renderDialog();
    api.importFile
      .mockResolvedValueOnce(report({}))
      .mockResolvedValueOnce(report({ dry_run: false, committed: true }));

    expect(screen.getByRole("button", { name: "Check file" }).hasAttribute("disabled")).toBe(true);
    const file = csv();
    await user.upload(screen.getByLabelText("File (.csv or .xlsx)"), file);
    await user.click(screen.getByRole("button", { name: "Check file" }));

    expect(await screen.findByText("Would create 2 employees.")).toBeTruthy();
    const [, sentFile, checkOptions] = api.importFile.mock.calls[0] as [
      string,
      File,
      ImportOptions,
    ];
    expect(sentFile).toBe(file);
    expect(checkOptions).toEqual({ dryRun: true, onError: "abort", onDuplicate: "error" });
    expect(onImported).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Import 2 employees" }));
    expect(await screen.findByText("Created 2 employees.")).toBeTruthy();
    expect((api.importFile.mock.calls[1] as [string, File, ImportOptions])[2].dryRun).toBe(false);
    expect(onImported).toHaveBeenCalledTimes(1);
    // Done: the footer's Cancel became Close (the dialog's corner X is also named "Close").
    expect(screen.queryByRole("button", { name: "Cancel" })).toBeNull();
    expect(screen.getAllByRole("button", { name: "Close" })).toHaveLength(2);
    expect(screen.queryByRole("button", { name: /^Import \d/ })).toBeNull();
  });

  it("lists row problems and does not offer Import when nothing may be written", async () => {
    const { user } = renderDialog();
    api.importFile.mockResolvedValueOnce(
      report({
        created: 1,
        failed: 1,
        rows: [
          {
            row: 3,
            status: "failed",
            errors: [{ column: "company", message: "No company named 'Nope'." }],
            warnings: [],
          },
        ],
      }),
    );
    await user.upload(screen.getByLabelText("File (.csv or .xlsx)"), csv());
    await user.click(screen.getByRole("button", { name: "Check file" }));

    expect(await screen.findByText("company: No company named 'Nope'.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Import \d/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Check file" })).toBeTruthy();
  });

  it("a changed option makes the last check stale", async () => {
    const { user } = renderDialog();
    api.importFile.mockResolvedValueOnce(report({}));
    await user.upload(screen.getByLabelText("File (.csv or .xlsx)"), csv());
    await user.click(screen.getByRole("button", { name: "Check file" }));
    await screen.findByRole("button", { name: "Import 2 employees" });

    await user.selectOptions(screen.getByLabelText("If a row has a problem"), "skip");
    expect(screen.queryByRole("button", { name: "Import 2 employees" })).toBeNull();
    expect(screen.queryByText("Would create 2 employees.")).toBeNull();
  });

  it("shows the server's message when the file is refused", async () => {
    const { user } = renderDialog();
    const { ApiError } = await import("../src/api/errors");
    api.importFile.mockRejectedValueOnce(
      new ApiError({ status: 422, message: "Missing required column(s): full_name." }),
    );
    await user.upload(screen.getByLabelText("File (.csv or .xlsx)"), csv());
    await user.click(screen.getByRole("button", { name: "Check file" }));
    expect(await screen.findByText("Missing required column(s): full_name.")).toBeTruthy();
  });

  it("does not offer 'update' for users", () => {
    renderDialog("users");
    const select = screen.getByLabelText(/If a user already exists/) as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(["error", "skip"]);
  });

  it("downloads the template", async () => {
    const { user } = renderDialog();
    api.downloadTemplate.mockResolvedValueOnce(undefined);
    await user.click(screen.getByRole("button", { name: /Download template/ }));
    expect(api.downloadTemplate).toHaveBeenCalledWith("employees");
  });
});
