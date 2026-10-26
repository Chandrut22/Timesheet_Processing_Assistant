import { createFileRoute } from "@tanstack/react-router";
import { EmployeesPage, validateEmployeesSearch } from "@/features/employees";

export const Route = createFileRoute("/_app/employees")({
  validateSearch: validateEmployeesSearch,
  component: EmployeesPage,
});
