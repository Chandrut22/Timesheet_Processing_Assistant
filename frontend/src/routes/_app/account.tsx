import { createFileRoute } from "@tanstack/react-router";
import { AccountPage } from "@/features/account/components/AccountPage";

export const Route = createFileRoute("/_app/account")({
  component: AccountPage,
});
