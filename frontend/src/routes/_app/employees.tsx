import { createFileRoute } from "@tanstack/react-router";
import { EmployeesPage } from "@/features/employees/components/EmployeesPage";
import { validateEmployeesSearch } from "@/features/employees/utils/employeesSearch";

export const Route = createFileRoute("/_app/employees")({
  validateSearch: validateEmployeesSearch,
  component: EmployeesPage,
});
