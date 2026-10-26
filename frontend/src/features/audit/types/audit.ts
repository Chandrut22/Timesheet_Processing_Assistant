import { z } from "zod";
import { isoDateTime, jsonObject, uuid } from "@/services/schemas";

export const AuditEventReadSchema = z.object({
  id: uuid,
  entity_type: z.string(),
  entity_id: uuid,
  action: z.string(),
  actor_id: uuid.nullable(),
  actor_name: z.string().nullable(),
  details: jsonObject,
  created_at: isoDateTime,
});

export type AuditEventRead = z.infer<typeof AuditEventReadSchema>;
