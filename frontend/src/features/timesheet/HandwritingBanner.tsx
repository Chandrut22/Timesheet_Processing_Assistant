import { useQuery } from "@tanstack/react-query";
import { coreApi } from "@/api/core";
import type { TimesheetRead } from "@/api/models";
import { qk } from "@/api/queryKeys";
import { Banner } from "@/components/States";
import { hasHandwrittenHours } from "@/lib/writing";

/**
 * For a timesheet from a photo / scan read by the vision model: a reminder to check the
 * values against the original (hours by hand), or that the page was hard to read.
 */
export function HandwritingBanner({ t }: { t: TimesheetRead }) {
  // The submission is also loaded (and cached) by the Source panel.
  const q = useQuery({
    queryKey: qk.submissions.detail(t.submission_id),
    queryFn: () => coreApi.getSubmission(t.submission_id),
  });
  const doc = q.data?.documents.find((d) => d.id === t.document_id);
  if (!doc || doc.read_method !== "vision") return null;
  if (doc.writing_class === "uncertain" || doc.writing_class === "no_text") {
    return (
      <Banner tone="danger" className="mb-4">
        The photo / scan was hard to read. Check every value against the original.
      </Banner>
    );
  }
  if (hasHandwrittenHours(doc)) {
    return (
      <Banner tone="warning" className="mb-4">
        Hours were written by hand and read by AI. Check them against the original.
        {doc.unclear_marks > 0
          ? ` ${doc.unclear_marks} value${doc.unclear_marks === 1 ? " was" : "s were"} unreadable and left out.`
          : ""}
      </Banner>
    );
  }
  return null;
}
