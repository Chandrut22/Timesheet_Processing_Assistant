import { createFileRoute } from "@tanstack/react-router";
import { HolidaysPage } from "@/features/holidays/components/HolidaysPage";
import { validateHolidaysSearch } from "@/features/holidays/utils/holidaysSearch";

export const Route = createFileRoute("/_app/holidays")({
  validateSearch: validateHolidaysSearch,
  component: HolidaysPage,
});
