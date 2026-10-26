// @vitest-environment jsdom
import userEvent from "@testing-library/user-event";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UploadDropzone } from "./UploadDropzone";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const props = { problems: [] as string[], onFiles: () => undefined };

describe("UploadDropzone", () => {
  it("opens the file picker with Enter and with Space", async () => {
    const click = vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(() => undefined);
    const user = userEvent.setup();
    render(<UploadDropzone {...props} fileCount={0} totalBytes={0} compact={false} />);
    const zone = screen.getByRole("button", { name: /choose files/i });
    zone.focus();
    await user.keyboard("{Enter}");
    await user.keyboard(" ");
    expect(click).toHaveBeenCalledTimes(2);
  });

  it("fills the panel with no files (state A) and is a slim bar with files (state B)", () => {
    render(<UploadDropzone {...props} fileCount={0} totalBytes={0} compact={false} />);
    const empty = screen.getByRole("button", { name: /Drag files anywhere on this page/ });
    expect(empty.dataset.state).toBe("empty");
    expect(screen.getByText("0 / 10 files")).toBeTruthy();
    cleanup();

    render(<UploadDropzone {...props} fileCount={3} totalBytes={3 * 1024 * 1024} compact />);
    const bar = screen.getByRole("button", { name: /Drop more files/ });
    expect(bar.dataset.state).toBe("compact");
    expect(screen.getByText(/^3 \/ 10 files · 3(\.0)? MB$/)).toBeTruthy();
  });

  it("does not open the picker while uploading", async () => {
    const click = vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(() => undefined);
    const user = userEvent.setup();
    render(<UploadDropzone {...props} fileCount={1} totalBytes={10} compact disabled />);
    await user.click(screen.getByRole("button", { name: /Drop more files/ }));
    expect(click).not.toHaveBeenCalled();
  });

  it("hands picked files over and announces problems politely", async () => {
    const onFiles = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <UploadDropzone
        problems={[]}
        onFiles={onFiles}
        fileCount={0}
        totalBytes={0}
        compact={false}
      />,
    );
    const picked = new File(["x"], "hours.csv", { type: "text/csv" });
    const input = screen.getByLabelText("Choose files to upload") as HTMLInputElement;
    await user.upload(input, picked);
    expect(onFiles).toHaveBeenCalledWith([picked]);
    expect(input.value).toBe(""); // reset, so the same file can be picked again

    rerender(
      <UploadDropzone
        problems={["setup.exe: this file type isn't supported."]}
        onFiles={onFiles}
        fileCount={0}
        totalBytes={0}
        compact={false}
      />,
    );
    const problem = screen.getByText("setup.exe: this file type isn't supported.");
    expect(problem.closest("[aria-live]")?.getAttribute("aria-live")).toBe("polite");
  });
});
