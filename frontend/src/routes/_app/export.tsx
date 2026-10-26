import { createFileRoute } from "@tanstack/react-router";
import { ExportPage, validateExportSearch } from "@/features/export";

export const Route = createFileRoute("/_app/export")({
  validateSearch: validateExportSearch,
  component: ExportPage,
});
