import { createFileRoute } from "@tanstack/react-router";
import { TimesheetPage } from "@/features/timesheets";

export const Route = createFileRoute("/_app/timesheets/$timesheetId")({
  component: TimesheetPage,
});
