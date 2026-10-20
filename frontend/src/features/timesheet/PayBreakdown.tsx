import { Calculator } from "lucide-react";
import type { TimesheetRead } from "@/api/models";
import { Money } from "@/components/Money";
import { Banner } from "@/components/States";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatHours, formatMoney } from "@/lib/format";

export function PayBreakdown({
  t,
  onRecalculate,
  recalculating,
  readOnly,
}: {
  t: TimesheetRead;
  onRecalculate: () => void;
  recalculating: boolean;
  readOnly: boolean;
}) {
  const rows = [
    { label: "Regular", hours: t.regular_hours, rate: t.hourly_rate, amount: t.regular_amount },
    { label: "Overtime", hours: t.overtime_hours, rate: t.overtime_rate, amount: t.overtime_amount },
    { label: "Double time", hours: t.double_time_hours, rate: t.double_time_rate, amount: t.double_time_amount },
    { label: "Holiday", hours: t.holiday_hours, rate: t.holiday_rate, amount: t.holiday_amount },
  ];
  // A missing amount only matters where there are hours to pay.
  const missing = rows.some((r) => r.hours > 0 && r.amount === null) || t.gross_amount === null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Pay</CardTitle>
        {!readOnly ? (
          <Button variant="outline" size="sm" onClick={onRecalculate} disabled={recalculating}>
            <Calculator /> {recalculating ? "Recalculating…" : "Recalculate"}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-3">
        {missing ? (
          <Banner tone="warning">
            A pay rate is missing for this company, so some amounts can't be worked out. Set the rate on the
            company, then press Recalculate.
          </Banner>
        ) : null}
        <dl className="divide-y text-sm">
          {rows.map((r) => (
            <div key={r.label} className="flex items-baseline justify-between gap-3 py-2">
              <dt className="text-muted-foreground">{r.label}</dt>
              <dd className="tabular text-right">
                <span className="text-muted-foreground">
                  {formatHours(r.hours)} h × {formatMoney(r.rate, t.currency) ?? "—"} ={" "}
                </span>
                {r.hours === 0 && r.amount === null ? (
                  <span>—</span>
                ) : (
                  <Money amount={r.amount} currency={t.currency} />
                )}
              </dd>
            </div>
          ))}
          <div className="flex items-baseline justify-between gap-3 pt-3">
            <dt className="font-medium">Gross ({formatHours(t.total_hours)} h)</dt>
            <dd className="text-base font-semibold">
              <Money amount={t.gross_amount} currency={t.currency} />
            </dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}
