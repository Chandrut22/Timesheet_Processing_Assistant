// What a route shows when it fails. A page whose code can't be loaded after a deploy
// gets "a new version is available" and a reload, not a generic error and a retry
// (retrying asks for the same missing file again).
import { RefreshCw } from "lucide-react";
import type { JSX } from "react";

import { ErrorState } from "@/components/common/States";
import { Button } from "@/components/ui/button";
import { isChunkLoadError } from "@/utils/chunkError";

export function RouteError({
  error,
  onRetry,
  reload = () => window.location.reload(),
}: {
  error: unknown;
  onRetry: () => void;
  /** Tests pass their own. */
  reload?: () => void;
}): JSX.Element {
  if (isChunkLoadError(error)) {
    return (
      <div
        role="alert"
        className="flex flex-col items-center gap-3 rounded-lg border border-dashed bg-card px-6 py-10 text-center"
      >
        <p className="text-sm font-medium">A new version of the app is available.</p>
        <p className="max-w-md text-sm text-muted-foreground">
          This page changed since you opened the app. Reload to get the new version; nothing you
          saved is lost.
        </p>
        <Button size="sm" onClick={reload}>
          <RefreshCw /> Reload
        </Button>
      </div>
    );
  }
  return <ErrorState error={error} onRetry={onRetry} />;
}
