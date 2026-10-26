import { http } from "@/lib/axios";
import { AuditEventReadSchema } from "../types/audit";
import { z } from "zod";
import { checked } from "@/services/response";

export const auditService = {
  listAuditEvents: (entityType: "timesheet" | "submission", entityId: string) =>
    checked(
      z.array(AuditEventReadSchema),
      http.get("/api/audit-events", {
        params: { entity_type: entityType, entity_id: entityId },
      }),
    ),
};
