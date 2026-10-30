import { createFileRoute } from "@tanstack/react-router";
import { TimesheetPage } from "@/features/timesheets/components/TimesheetPage";

export const Route = createFileRoute("/_app/timesheets/$timesheetId")({
  component: TimesheetPage,
});
