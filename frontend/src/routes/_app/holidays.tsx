import { createFileRoute } from "@tanstack/react-router";
import { HolidaysPage, validateHolidaysSearch } from "@/features/holidays";

export const Route = createFileRoute("/_app/holidays")({
  validateSearch: validateHolidaysSearch,
  component: HolidaysPage,
});
