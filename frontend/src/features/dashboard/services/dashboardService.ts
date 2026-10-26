import { http } from "@/lib/axios";
import { DashboardSnapshotSchema } from "../types/dashboard";
import { checked } from "@/services/response";

export const dashboardService = {
  getDashboard: () => checked(DashboardSnapshotSchema, http.get("/api/dashboard")),
};
