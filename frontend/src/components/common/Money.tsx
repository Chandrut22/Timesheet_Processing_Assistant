import { formatMoney } from "@/utils/format";
import type { JSX } from "react";

export function Money({
  amount,
  currency,
  missingLabel = "rate missing",
}: {
  amount: number | null | undefined;
  currency?: string | null;
  missingLabel?: string;
}): JSX.Element {
  const text = formatMoney(amount, currency);
  if (text === null)
    return <span className="text-xs font-medium text-amber-700">{missingLabel}</span>;
  return <span className="tabular">{text}</span>;
}
