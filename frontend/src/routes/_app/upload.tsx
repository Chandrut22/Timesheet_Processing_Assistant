import { createFileRoute } from "@tanstack/react-router";
import { UploadPage } from "@/features/upload/components/UploadPage";

export const Route = createFileRoute("/_app/upload")({
  staticData: { fullWidth: true },
  component: UploadPage,
});
