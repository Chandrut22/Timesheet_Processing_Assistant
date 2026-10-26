import { z } from "zod";
import { SubmissionReadSchema } from "@/features/submissions";

export const DashboardSnapshotSchema = z.object({
  counts: z.object({
    needs_review: z.number().int(),
    high_severity: z.number().int(),
    approved_waiting_export: z.number().int(),
    failed_submissions: z.number().int(),
  }),
  recent: z.array(SubmissionReadSchema),
});

export type DashboardSnapshot = z.infer<typeof DashboardSnapshotSchema>;
