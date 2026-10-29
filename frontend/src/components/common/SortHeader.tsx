import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { TableHead } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { JSX } from "react";

export function SortHeader<K extends string>({
  label,
  sortKey,
  current,
  order,
  onSort,
  className,
}: {
  label: string;
  sortKey: K;
  current: K;
  order: "asc" | "desc";
  onSort: (key: K) => void;
  className?: string;
}): JSX.Element {
  const active = current === sortKey;
  const Icon = !active ? ArrowUpDown : order === "asc" ? ArrowUp : ArrowDown;
  return (
    <TableHead
      className={className}
      aria-sort={active ? (order === "asc" ? "ascending" : "descending") : "none"}
    >
      <button
        type="button"
        className={cn(
          "inline-flex items-center gap-1 rounded hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none",
          active && "text-foreground",
        )}
        onClick={() => onSort(sortKey)}
      >
        {label}
        <Icon className="size-3.5" aria-hidden />
      </button>
    </TableHead>
  );
}
