// The in-app Back link. It goes back exactly like the browser's Back button (same
// page, same filters, page number and selected item, no new history entry), and only
// falls back to a fixed page when this tab has no earlier page in the app: the page
// was opened from a link, a bookmark or a new tab.
import { Link, useCanGoBack, useRouter } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import type { MouseEvent, JSX } from "react";

/** Pages a Back link may fall back to (typed, so a renamed route fails the build). */
export type BackFallback = "/" | "/submissions" | "/review" | "/companies";

/** A plain left click (not Ctrl / Cmd / Shift / Alt, not the middle button). */
function isPlainLeftClick(e: MouseEvent): boolean {
  return e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey;
}

export function BackButton({
  fallback,
  fallbackLabel,
}: {
  /** Where to go when there is no earlier page in this tab. */
  fallback: BackFallback;
  /** Shown instead of "Back" in that case, e.g. "Submissions". */
  fallbackLabel: string;
}): JSX.Element {
  const router = useRouter();
  const canGoBack = useCanGoBack();

  return (
    // A real link to the fallback, so Ctrl-click / middle-click open it in a new tab.
    <Link
      to={fallback}
      className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
      onClick={(e) => {
        if (!canGoBack || !isPlainLeftClick(e)) return; // the Link opens `fallback`
        e.preventDefault(); // the Link skips its own navigation
        router.history.back();
      }}
    >
      <ArrowLeft className="size-4" aria-hidden /> {canGoBack ? "Back" : fallbackLabel}
    </Link>
  );
}
