// Public API of the employees feature: other parts of the app import only from here.
// Pages are not exported: only their route files import them (src/routes), so each
// page stays in its own chunk (autoCodeSplitting).
export { useEmployeeMap } from "./hooks/useEmployeeMap";
export { employeeKeys } from "./queries/employeeQueries";
export { employeeService } from "./services/employeeService";
export { EmployeePageSchema, EmployeeReadSchema } from "./types/employee";
export { useEmployeesList } from "./hooks/useEmployeesList";
export type {
  EmployeeCreate,
  EmployeeListParams,
  EmployeeRead,
  EmployeeUpdate,
} from "./types/employee";
export { useEmployeeSearch } from "./hooks/useEmployeeSearch";
