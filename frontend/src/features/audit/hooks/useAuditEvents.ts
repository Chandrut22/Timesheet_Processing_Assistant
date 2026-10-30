import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { auditKeys } from "../queries/auditQueries";
import { auditService } from "../services/auditService";

type AuditEvents = Awaited<ReturnType<typeof auditService.listAuditEvents>>;

/** Who changed what, and when, for one timesheet or submission. */
export function useAuditEvents(
  entityType: "timesheet" | "submission",
  entityId: string,
): UseQueryResult<AuditEvents> {
  return useQuery({
    queryKey: auditKeys.entity(entityType, entityId),
    queryFn: () => auditService.listAuditEvents(entityType, entityId),
  });
}
