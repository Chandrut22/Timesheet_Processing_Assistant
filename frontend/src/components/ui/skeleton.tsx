import type * as React from "react";
import { cn } from "@/lib/utils";
import type { JSX } from "react";

export function Skeleton({ className, ...props }: React.ComponentProps<"div">): JSX.Element {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />;
}
