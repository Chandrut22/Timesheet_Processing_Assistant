import { cn } from "@/lib/utils";

export function JsonBlock({ value, className }: { value: unknown; className?: string }) {
  const text =
    typeof value === "string" ? value : (JSON.stringify(value ?? null, null, 2) ?? String(value));
  return (
    <pre
      className={cn(
        "max-h-80 overflow-auto rounded-md border bg-muted/60 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap break-words",
        className,
      )}
    >
      {text}
    </pre>
  );
}
