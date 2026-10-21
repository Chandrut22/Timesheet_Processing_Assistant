// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/lib/lookups", () => ({ useCompanies: () => ({ data: [], isLoading: false }) }));
const { UploadSettings } = await import("../src/features/ingestion/UploadSettings");

const base = {
  companyId: "",
  onCompany: () => undefined,
  error: null,
  totalBytes: 0,
  progress: null,
  onUpload: () => undefined,
};
afterEach(cleanup);

describe("UploadSettings", () => {
  it("disables Upload with no files", () => {
    render(<UploadSettings {...base} fileCount={0} pending={false} />);
    expect(screen.getByRole("button", { name: /Upload files/ }).hasAttribute("disabled")).toBe(
      true,
    );
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("names the file count when ready", () => {
    render(<UploadSettings {...base} fileCount={3} totalBytes={2048} pending={false} />);
    const button = screen.getByRole("button", { name: /Upload 3 files/ });
    expect(button.hasAttribute("disabled")).toBe(false);
  });

  it("shows the progress while uploading", () => {
    render(<UploadSettings {...base} fileCount={2} pending progress={42} />);
    expect(screen.getByRole("button", { name: /Uploading… 42%/ }).hasAttribute("disabled")).toBe(
      true,
    );
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("42");
  });
});
