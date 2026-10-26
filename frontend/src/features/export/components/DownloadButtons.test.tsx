// @vitest-environment jsdom
// The two download buttons, through the real exportService.downloadExport and the shared axios
// client (only the network adapter and the "save file" step are replaced).
import userEvent from "@testing-library/user-event";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/services/session", () => ({
  getAccessToken: () => "token",
  refreshAccessToken: async () => null,
}));
const saved = vi.hoisted(() => [] as { name: string; type: string }[]);
vi.mock("@/lib/axios", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/axios")>()),
  saveBlob: (blob: Blob, name: string) => saved.push({ name, type: blob.type }),
}));
const toastError = vi.hoisted(() => vi.fn());
vi.mock("sonner", () => ({ toast: { error: toastError, success: vi.fn() } }));

const { http } = await import("@/lib/axios");
const { exportFileName } = await import("../services/exportService");
const { DownloadButtons } = await import("./DownloadButtons");

const batch = { id: "b1", filename: "payroll_lakeside_2026-09-07_ab12cd34.csv" };
let requests: InternalAxiosRequestConfig[] = [];

function serve(status: number, headers: Record<string, string> = {}) {
  http.defaults.adapter = async (config) => {
    requests.push(config);
    const format = (config.params as { format: string }).format;
    const type =
      format === "xlsx"
        ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        : "text/csv";
    // The error body as a parsed object: errors.ts reads a Blob body the same way.
    const data = status === 200 ? new Blob(["x"], { type }) : { detail: "x", code: "rate_limited" };
    const response = { status, statusText: "", headers, config, data };
    if (status >= 400) {
      const { AxiosError } = await import("axios");
      throw new AxiosError("failed", "ERR_BAD_RESPONSE", config, null, response);
    }
    return response;
  };
}

beforeEach(() => {
  requests = [];
  saved.length = 0;
  toastError.mockReset();
});
afterEach(cleanup);

describe("download buttons", () => {
  it.each([
    ["Download CSV", "csv", ".csv"],
    ["Download Excel (.xlsx)", "xlsx", ".xlsx"],
  ])("%s asks for format=%s and saves a %s file", async (label, format, extension) => {
    serve(200); // no Content-Disposition: the name comes from the batch
    const user = userEvent.setup();
    render(<DownloadButtons batch={batch} />);
    await user.click(screen.getByRole("button", { name: label }));

    await waitFor(() => expect(saved).toHaveLength(1));
    expect(requests).toHaveLength(1);
    expect(requests[0].url).toBe("/api/exports/b1/download");
    expect(requests[0].params).toEqual({ format });
    expect(requests[0].responseType).toBe("blob");
    expect(saved[0].name.endsWith(extension)).toBe(true);
    expect(saved[0].name).toBe(`payroll_lakeside_2026-09-07_ab12cd34${extension}`);
  });

  it("uses the server's file name when it sends one", async () => {
    serve(200, { "content-disposition": 'attachment; filename="payroll_from_server.xlsx"' });
    const user = userEvent.setup();
    render(<DownloadButtons batch={batch} />);
    await user.click(screen.getByRole("button", { name: "Download Excel (.xlsx)" }));
    await waitFor(() => expect(saved.map((s) => s.name)).toEqual(["payroll_from_server.xlsx"]));
  });

  it("shows the shared client's message when rate limited", async () => {
    serve(429, { "retry-after": "12" });
    const user = userEvent.setup();
    render(<DownloadButtons batch={batch} />);
    await user.click(screen.getByRole("button", { name: "Download CSV" }));
    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith("Too many requests. Try again in 12 seconds."),
    );
    expect(saved).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Download CSV" })).toBeTruthy(); // not stuck busy
  });
});

describe("exportFileName", () => {
  it("swaps the extension for the chosen format", () => {
    expect(exportFileName(batch, "xlsx")).toBe("payroll_lakeside_2026-09-07_ab12cd34.xlsx");
    expect(exportFileName(batch, "csv")).toBe("payroll_lakeside_2026-09-07_ab12cd34.csv");
    expect(exportFileName({ id: "b2", filename: "" }, "xlsx")).toBe("payroll-b2.xlsx");
  });
});
