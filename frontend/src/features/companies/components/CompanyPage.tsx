import { getRouteApi, Link } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState, type JSX } from "react";
import { toast } from "sonner";
import { errorMessage, isApiError } from "@/services/apiErrors";
import type { CompanyRead, WhitelistRead } from "../types/company";
import { useIsAdmin } from "@/features/auth";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { FormError } from "@/components/forms/Field";
import { PageHeader } from "@/components/common/PageHeader";
import { BlockSkeleton, EmptyState, ErrorState } from "@/components/common/States";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { useCompanyDetails } from "@/features/companies";
import { useCompanyWhitelist } from "@/features/companies";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CompanyForm, type CompanyFormValues } from "./CompanyForm";
import { toCompanyBody } from "../utils/companyUtils";
import { formatDate, humanize } from "@/utils/format";
import { companyService } from "../services/companyService";
import { companyKeys } from "../queries/companyQueries";
import { BackButton } from "@/components/common/BackButton";

const routeApi = getRouteApi("/_app/companies/$companyId");

type CompanySearch = { tab?: "details" | "senders" };

export function CompanyPage(): JSX.Element {
  const { companyId } = routeApi.useParams();
  const { tab } = routeApi.useSearch();
  const navigate = routeApi.useNavigate();
  const q = useCompanyDetails(companyId);

  const back = <BackButton fallback="/companies" fallbackLabel="Companies" />;

  if (q.isPending)
    return (
      <>
        <PageHeader title="Company" back={back} />
        <BlockSkeleton className="h-80" />
      </>
    );
  if (q.isError)
    return (
      <>
        <PageHeader title="Company" back={back} />
        {isApiError(q.error, 404) ? (
          <EmptyState title="Company not found" />
        ) : (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        )}
      </>
    );

  const c = q.data;
  return (
    <>
      <PageHeader
        back={back}
        title={c.name}
        description={
          <span className="flex items-center gap-2">
            <Badge variant={c.is_active ? "success" : "muted"}>
              {c.is_active ? "Active" : "Inactive"}
            </Badge>
            <span>Currency {c.currency}</span>
          </span>
        }
        actions={
          <Button asChild variant="outline">
            <Link to="/employees" search={{ company_id: c.id }}>
              Employees
            </Link>
          </Button>
        }
      />
      <Tabs
        value={tab ?? "details"}
        onValueChange={(v) =>
          void navigate({ search: { tab: v === "senders" ? "senders" : undefined }, replace: true })
        }
      >
        <TabsList>
          <TabsTrigger value="details">Rates and rules</TabsTrigger>
          <TabsTrigger value="senders">Allowed senders</TabsTrigger>
        </TabsList>
        <TabsContent value="details">
          <DetailsTab company={c} />
        </TabsContent>
        <TabsContent value="senders">
          <WhitelistTab company={c} />
        </TabsContent>
      </Tabs>
    </>
  );
}

function DetailsTab({ company }: { company: CompanyRead }): JSX.Element {
  const isAdmin = useIsAdmin();
  const queryClient = useQueryClient();
  const update = useMutation({
    mutationFn: (v: CompanyFormValues) =>
      companyService.updateCompany(company.id, { ...toCompanyBody(v), is_active: v.is_active }),
    meta: { silentError: true },
    onSuccess: (c) => {
      queryClient.setQueryData(companyKeys.detail(c.id), c);
      void queryClient.invalidateQueries({ queryKey: companyKeys.all });
      toast.success("Saved. New rates apply to timesheets calculated from now on.");
    },
  });
  return (
    <Card>
      <CardContent className="pt-5">
        {!isAdmin ? (
          <p className="mb-4 text-sm text-muted-foreground">Only admins can change companies.</p>
        ) : null}
        <CompanyForm
          key={company.updated_at}
          company={company}
          readOnly={!isAdmin}
          submitLabel="Save changes"
          onSubmit={(v) => update.mutateAsync(v)}
          serverError={update.error ? errorMessage(update.error) : null}
        />
      </CardContent>
    </Card>
  );
}

function WhitelistTab({ company }: { company: CompanyRead }): JSX.Element {
  const isAdmin = useIsAdmin();
  const queryClient = useQueryClient();
  const [value, setValue] = useState("");
  const [removing, setRemoving] = useState<WhitelistRead | null>(null);
  const list = useCompanyWhitelist(company.id);

  const add = useMutation({
    mutationFn: (v: string) => companyService.addWhitelist(company.id, v),
    meta: { silentError: true },
    onSuccess: (entry) => {
      setValue("");
      toast.success(`Added ${entry.value}.`);
      void queryClient.invalidateQueries({ queryKey: companyKeys.whitelist(company.id) });
    },
  });
  const remove = useMutation({
    mutationFn: (entry: WhitelistRead) => companyService.removeWhitelist(company.id, entry.id),
    onSuccess: () => {
      setRemoving(null);
      toast.success("Removed.");
      void queryClient.invalidateQueries({ queryKey: companyKeys.whitelist(company.id) });
    },
  });

  const trimmed = value.trim().toLowerCase();
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Allowed senders</CardTitle>
          <CardDescription>
            Emails from these addresses or domains are accepted as {company.name}'s timesheets.
            Everything else is ignored.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {isAdmin ? (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (trimmed.length >= 3) add.mutate(trimmed);
            }}
          >
            <div className="grid w-full max-w-sm gap-1.5">
              <Label htmlFor="wl-value">Email or domain</Label>
              <Input
                id="wl-value"
                placeholder="payroll@acme.com or acme.com"
                value={value}
                maxLength={255}
                onChange={(e) => setValue(e.target.value)}
              />
            </div>
            <Button type="submit" disabled={trimmed.length < 3 || add.isPending}>
              <Plus /> {add.isPending ? "Adding…" : "Add"}
            </Button>
          </form>
        ) : null}
        <FormError message={add.error ? errorMessage(add.error) : null} />

        {list.isPending ? (
          <BlockSkeleton className="h-24" />
        ) : list.isError ? (
          <ErrorState error={list.error} onRetry={() => void list.refetch()} />
        ) : list.data.length === 0 ? (
          <EmptyState
            title="No senders yet"
            hint="Until one is added, no emails are accepted for this company."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Sender</TableHead>
                <TableHead>Kind</TableHead>
                <TableHead>Added</TableHead>
                {isAdmin ? <TableHead className="w-10" /> : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.data.map((w) => (
                <TableRow key={w.id}>
                  <TableCell className="font-medium">{w.value}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">{humanize(w.kind)}</Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDate(w.created_at)}
                  </TableCell>
                  {isAdmin ? (
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Remove ${w.value}`}
                        onClick={() => setRemoving(w)}
                      >
                        <Trash2 />
                      </Button>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={`Remove ${removing?.value ?? ""}?`}
        description="Emails from this sender will no longer be accepted for this company."
        confirmLabel="Remove"
        destructive
        pending={remove.isPending}
        onConfirm={() => removing && remove.mutate(removing)}
      />
    </Card>
  );
}

/** The page's search params, checked when the URL changes. */
export const validateCompanySearch = (s: Record<string, unknown>): CompanySearch => ({
  tab: s.tab === "senders" ? "senders" : undefined,
});
