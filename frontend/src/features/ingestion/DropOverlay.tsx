// Shown over the whole page while files are dragged over the window.
import { CloudUpload } from "lucide-react";

export function DropOverlay({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <div
      data-testid="drop-overlay"
      className="pointer-events-none absolute inset-0 z-40 grid place-items-center rounded-lg border-2 border-dashed border-primary bg-primary/10 backdrop-blur-[1px]"
    >
      <p className="flex items-center gap-2 rounded-md bg-card px-4 py-2 text-base font-medium shadow-sm">
        <CloudUpload className="size-5 text-primary" aria-hidden /> Drop files to add them
      </p>
    </div>
  );
}
