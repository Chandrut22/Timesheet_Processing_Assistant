import type { EmployeeCreate, EmployeeUpdate } from "../types/employee";
import { splitList } from "@/utils/format";
import type { EmployeeFormValues } from "../components/EmployeeForm";

export function toEmployeeCreate(v: EmployeeFormValues): EmployeeCreate {
  return {
    company_id: v.company_id,
    employee_code: v.employee_code.trim(),
    full_name: v.full_name.trim(),
    email: v.email.trim() || null,
    aliases: splitList(v.aliases),
    assignment_start: v.assignment_start || null,
    assignment_end: v.assignment_end || null,
  };
}

export function toEmployeeUpdate(v: EmployeeFormValues): EmployeeUpdate {
  const { company_id: _ignored, ...rest } = toEmployeeCreate(v);
  void _ignored; // company can't change: an employee's history belongs to one company
  return { ...rest, is_active: v.is_active };
}
