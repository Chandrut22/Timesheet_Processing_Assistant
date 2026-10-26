import { createFileRoute } from "@tanstack/react-router";
import { CompanyPage, validateCompanySearch } from "@/features/companies";

export const Route = createFileRoute("/_app/companies/$companyId")({
  validateSearch: validateCompanySearch,
  component: CompanyPage,
});
