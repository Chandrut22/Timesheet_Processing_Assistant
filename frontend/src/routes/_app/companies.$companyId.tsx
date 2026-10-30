import { createFileRoute } from "@tanstack/react-router";
import { CompanyPage } from "@/features/companies/components/CompanyPage";
import { validateCompanySearch } from "@/features/companies/utils/companySearch";

export const Route = createFileRoute("/_app/companies/$companyId")({
  validateSearch: validateCompanySearch,
  component: CompanyPage,
});
