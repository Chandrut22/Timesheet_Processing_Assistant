// Shown while a page's code (its own chunk) or its route data is loading: the outline
// of a page, so the layout doesn't jump when it arrives.
import type { JSX } from "react";

import { Skeleton } from "@/components/ui/skeleton";

export function PagePending(): JSX.Element {
  return (
    <div aria-busy="true" aria-label="Loading page" className="space-y-4">
      <Skeleton className="h-8 w-56" />
      <Skeleton className="h-4 w-96 max-w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}
