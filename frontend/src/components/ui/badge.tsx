import type * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

export const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center gap-1 whitespace-nowrap rounded-md border px-2 py-0.5 text-xs font-medium [&>svg]:size-3",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary/10 text-primary",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "text-foreground",
        high: "border-red-200 bg-red-50 text-red-800",
        medium: "border-amber-200 bg-amber-50 text-amber-800",
        low: "border-sky-200 bg-sky-50 text-sky-800",
        success: "border-emerald-200 bg-emerald-50 text-emerald-800",
        danger: "border-red-200 bg-red-50 text-red-800",
        warning: "border-amber-200 bg-amber-50 text-amber-800",
        info: "border-sky-200 bg-sky-50 text-sky-800",
        muted: "border-transparent bg-muted text-muted-foreground",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>["variant"]>;

export function Badge({
  className,
  variant,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return (
    <span data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}
