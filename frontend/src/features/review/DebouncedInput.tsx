import { useEffect, useState } from "react";
import type * as React from "react";
import { Input } from "@/components/ui/input";

/** Text input that updates the URL only after typing pauses. */
export function DebouncedInput({
  value,
  onCommit,
  delay = 400,
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

  useEffect(() => {
    if (draft === value) return;
    const t = setTimeout(() => {
      setLastCommitted(draft);
      onCommit(draft);
    }, delay);
    return () => clearTimeout(t);
  }, [draft, value, delay, onCommit]);

  return <Input value={draft} onChange={(e) => setDraft(e.target.value)} {...props} />;
}
