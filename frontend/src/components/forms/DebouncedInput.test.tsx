// @vitest-environment jsdom
// The search box: every keystroke shows at once, the search runs once typing pauses.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState, type JSX } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DebouncedInput } from "./DebouncedInput";

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

/** A page that keeps the committed search like the real ones (in state / the URL). */
function Page({
  onCommit,
  initial = "",
}: {
  onCommit: (v: string) => void;
  initial?: string;
}): JSX.Element {
  const [q, setQ] = useState(initial);
  return (
    <>
      <DebouncedInput
        aria-label="Search"
        value={q}
        onCommit={(v) => {
          onCommit(v);
          setQ(v);
        }}
      />
      <button type="button" onClick={() => setQ("")}>
        Reset filters
      </button>
      <output>{q}</output>
    </>
  );
}

const box = (): HTMLInputElement =>
  screen.getByRole("textbox", { name: "Search" }) as HTMLInputElement;
const type = (text: string): boolean => fireEvent.change(box(), { target: { value: text } });

describe("DebouncedInput", () => {
  it("shows each keystroke at once but searches once, for the final text", () => {
    const commit = vi.fn();
    render(<Page onCommit={commit} />);
    for (const text of ["l", "la", "lak", "lake"]) type(text);
    expect(box().value).toBe("lake");
    act(() => vi.advanceTimersByTime(299));
    expect(commit).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(commit).toHaveBeenCalledExactlyOnceWith("lake");
  });

  it("sends the trimmed text, and nothing when it equals the current search", () => {
    const commit = vi.fn();
    render(<Page onCommit={commit} initial="lake" />);
    type("lake ");
    act(() => vi.advanceTimersByTime(300));
    type("lakes");
    type("lake");
    act(() => vi.advanceTimersByTime(300));
    expect(commit).not.toHaveBeenCalled();
    type("  side ");
    act(() => vi.advanceTimersByTime(300));
    expect(commit).toHaveBeenCalledExactlyOnceWith("side");
    expect(box().value).toBe("  side "); // what was typed stays in the box
  });

  it("Enter searches straight away", () => {
    const commit = vi.fn();
    render(<Page onCommit={commit} />);
    type("grace");
    fireEvent.keyDown(box(), { key: "Enter" });
    expect(commit).toHaveBeenCalledExactlyOnceWith("grace");
    act(() => vi.advanceTimersByTime(300));
    expect(commit).toHaveBeenCalledTimes(1);
  });

  it("clearing the box searches for nothing, which shows the full list", () => {
    const commit = vi.fn();
    render(<Page onCommit={commit} initial="grace" />);
    type("");
    act(() => vi.advanceTimersByTime(300));
    expect(commit).toHaveBeenCalledExactlyOnceWith("");
  });

  it("Reset filters clears the box and wins over a search still waiting", () => {
    const commit = vi.fn();
    render(<Page onCommit={commit} initial="grace" />);
    type("hopper");
    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(box().value).toBe("");
    act(() => vi.advanceTimersByTime(300));
    expect(commit).not.toHaveBeenCalled();
    expect(screen.getByRole("status").textContent).toBe("");
  });
});
