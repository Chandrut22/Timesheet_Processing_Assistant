import type * as React from "react";
import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { SEARCH_DEBOUNCE_MS } from "@/config/constants";
import { useDebouncedCallback } from "@/hooks/useDebounce";

/**
 * A search box: shows every keystroke at once and calls `onCommit` with the trimmed
 * text only after typing pauses (`delay`, 300 ms by default) or on Enter. Nothing is
 * committed when the trimmed text equals the current `value`, so a stray space or a
 * letter typed and deleted sends no request.
 */
export function DebouncedInput({
  value,
  onCommit,
  delay = SEARCH_DEBOUNCE_MS,
  onKeyDown,
  ...props
}: Omit<React.ComponentProps<"input">, "value" | "onChange"> & {
  value: string;
  onCommit: (value: string) => void;
  delay?: number;
}) {
  const [draft, setDraft] = useState(value);
  const [synced, setSynced] = useState(value);
  const [lastCommitted, setLastCommitted] = useState(value);

  // Follow outside changes (e.g. "Reset filters"), but not the echo of our own commit.
  if (value !== synced) {
    setSynced(value);
    if (value !== lastCommitted) setDraft(value);
  }

  const commit = useDebouncedCallback((text: string) => {
    const next = text.trim();
    if (next === value.trim()) return;
    setLastCommitted(next);
    onCommit(next);
  }, delay);

  // An outside change wins over a commit still waiting from earlier typing.
  useEffect(() => {
    if (value !== lastCommitted) commit.cancel();
  }, [value, lastCommitted, commit]);

  return (
    <Input
      value={draft}
      onChange={(e) => {
        setDraft(e.target.value);
        commit(e.target.value);
      }}
      onKeyDown={(e) => {
        onKeyDown?.(e);
        if (e.key === "Enter" && !e.defaultPrevented) {
          commit(e.currentTarget.value);
          commit.flush();
        }
      }}
      {...props}
    />
  );
}
