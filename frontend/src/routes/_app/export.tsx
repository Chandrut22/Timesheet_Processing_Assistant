import { createFileRoute } from "@tanstack/react-router";
import { ExportPage } from "@/features/export/components/ExportPage";
import { validateExportSearch } from "@/features/export/utils/exportSearch";

export const Route = createFileRoute("/_app/export")({
  validateSearch: validateExportSearch,
  component: ExportPage,
});
