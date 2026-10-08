import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  component: () => <div className="p-4 text-2xl font-bold">Review queue</div>,
});