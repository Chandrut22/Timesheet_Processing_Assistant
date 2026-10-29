// "Copy holidays": give other companies (a new client, say) the holidays one company
// already has, for one year or all of them. Dates a company already has are skipped.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Copy } from "lucide-react";
import { useState, type JSX } from "react";
import { toast } from "sonner";
import { CompanySelect, useCompanyMap } from "@/features/companies";
import { Field, FormError } from "@/components/forms/Field";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { NativeSelect } from "@/components/ui/input";
import { errorMessage } from "@/services/apiErrors";
import { holidayKeys } from "../queries/holidayQueries";
import { holidayService } from "../services/holidayService";
import { describeBulkResult } from "../utils/bulkResult";
import { CompanyChecklist } from "./CompanyChecklist";

export function CopyHolidaysDialog({
  years,
  defaultYear,
}: {
  years: number[];
  defaultYear: number;
}): JSX.Element {
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState<string[]>([]);
  const [year, setYear] = useState(String(defaultYear));
  const companies = useCompanyMap();
  const queryClient = useQueryClient();
  const copy = useMutation({
    mutationFn: () =>
      holidayService.copyHolidays({
        from_company_id: from,
        to_company_ids: to,
        year: year ? Number(year) : undefined,
      }),
    meta: { silentError: true },
    onSuccess: (result) => {
      toast.success(
        describeBulkResult(result, (id) => companies.get(id)?.name ?? "A company", {
          one: "holiday",
          many: "holidays",
        }),
      );
      void queryClient.invalidateQueries({ queryKey: holidayKeys.all });
      setOpen(false);
    },
  });
  const close = (o: boolean): void => {
    setOpen(o);
    if (!o) {
      copy.reset();
      setFrom("");
      setTo([]);
    }
  };

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <Copy /> Copy holidays
      </Button>
      <Dialog open={open} onOpenChange={close}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Copy holidays</DialogTitle>
            <DialogDescription>
              Give other companies the holidays one company already has. A date a company already
              has is left as it is.
            </DialogDescription>
          </DialogHeader>
          <FormError message={copy.error ? errorMessage(copy.error) : null} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Copy from" htmlFor="copy-from">
              <CompanySelect
                id="copy-from"
                value={from}
                onChange={(id) => {
                  setFrom(id);
                  setTo((t) => t.filter((c) => c !== id));
                }}
                includeAll={false}
              />
            </Field>
            <Field label="Year" htmlFor="copy-year">
              <NativeSelect id="copy-year" value={year} onChange={(e) => setYear(e.target.value)}>
                {years.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
                <option value="">All years</option>
              </NativeSelect>
            </Field>
          </div>
          <CompanyChecklist
            id="copy-to"
            label="Copy to"
            value={to}
            onChange={setTo}
            exclude={from || undefined}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => close(false)} disabled={copy.isPending}>
              Cancel
            </Button>
            <Button
              onClick={() => copy.mutate()}
              disabled={!from || to.length === 0 || copy.isPending}
            >
              {copy.isPending
                ? "Copying…"
                : to.length === 0
                  ? "Copy"
                  : `Copy to ${to.length} ${to.length === 1 ? "company" : "companies"}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
