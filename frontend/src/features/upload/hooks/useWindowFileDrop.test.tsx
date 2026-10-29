// @vitest-environment jsdom
// Page-wide drag and drop (useWindowFileDrop + DropOverlay, as the Upload page uses them).
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DropOverlay } from "../components/DropOverlay";
import { useWindowFileDrop } from "./useWindowFileDrop";
import type { JSX } from "react";

function Page({
  onFiles,
  enabled = true,
}: {
  onFiles: (f: File[]) => void;
  enabled?: boolean;
}): JSX.Element {
  const { dragging } = useWindowFileDrop(onFiles, { enabled });
  return <DropOverlay visible={dragging} />;
}

/** jsdom has no DragEvent / DataTransfer: a plain event carrying the fields we read. */
function drag(type: string, types: string[], files: File[] = []): Event {
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.defineProperty(event, "dataTransfer", { value: { types, files, dropEffect: "none" } });
  act(() => {
    window.dispatchEvent(event);
  });
  return event;
}

const overlay = (): HTMLElement | null => screen.queryByText("Drop files to add them");

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("page-wide drop", () => {
  it("shows the overlay for a file drag, and keeps it while crossing child elements", () => {
    render(<Page onFiles={() => undefined} />);
    drag("dragenter", ["Files"]);
    expect(overlay()).toBeTruthy();
    drag("dragenter", ["Files"]); // entering a child
    drag("dragleave", ["Files"]); // leaving the previous element
    expect(overlay()).toBeTruthy();
    drag("dragleave", ["Files"]); // left the window
    expect(overlay()).toBeNull();
  });

  it("ignores text and link drags", () => {
    render(<Page onFiles={() => undefined} />);
    drag("dragenter", ["text/plain", "text/uri-list"]);
    expect(overlay()).toBeNull();
  });

  it("adds dropped files and stops the browser from opening them", () => {
    const onFiles = vi.fn();
    render(<Page onFiles={onFiles} />);
    const f = new File(["x"], "week.pdf");
    drag("dragenter", ["Files"]);
    const over = drag("dragover", ["Files"]);
    const drop = drag("drop", ["Files"], [f]);
    expect(over.defaultPrevented).toBe(true);
    expect(drop.defaultPrevented).toBe(true);
    expect(onFiles).toHaveBeenCalledWith([f]);
    expect(overlay()).toBeNull();
  });

  it("still blocks a stray drop while uploading, but adds nothing", () => {
    const onFiles = vi.fn();
    render(<Page onFiles={onFiles} enabled={false} />);
    const drop = drag("drop", ["Files"], [new File(["x"], "week.pdf")]);
    expect(drop.defaultPrevented).toBe(true);
    expect(onFiles).not.toHaveBeenCalled();
  });

  it("removes its window listeners on unmount", () => {
    const remove = vi.spyOn(window, "removeEventListener");
    const { unmount } = render(<Page onFiles={() => undefined} />);
    unmount();
    const removed = remove.mock.calls.map(([type]) => type);
    expect(removed).toEqual(expect.arrayContaining(["dragenter", "dragleave", "dragover", "drop"]));
    expect(drag("drop", ["Files"], [new File(["x"], "a.pdf")]).defaultPrevented).toBe(false);
  });
});
