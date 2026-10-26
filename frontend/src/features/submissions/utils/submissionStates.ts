/** Submission states in which the worker is still busy (the UI polls while one is). */
export const IN_PROGRESS_STATES: ReadonlySet<string> = new Set([
  "received",
  "reading",
  "matching",
  "rule_checks",
  "reprocessing",
]);
