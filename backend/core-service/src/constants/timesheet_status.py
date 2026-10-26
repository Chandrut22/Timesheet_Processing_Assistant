from enum import StrEnum


class SubmissionSource(StrEnum):
    EMAIL = "email"
    UPLOAD = "upload"


class SubmissionStatus(StrEnum):
    """One email or one upload, as it moves through the pipeline."""

    RECEIVED = "received"  # saved, waiting for the worker
    PROCESSING = "processing"  # the worker is on it
    PROCESSED = "processed"  # every document handled (timesheets have their own status)
    FAILED = "failed"  # the pipeline crashed; can be reprocessed
    IGNORED = "ignored"  # an email we keep a record of but never process


class TimesheetStatus(StrEnum):
    """One person's week, extracted from a document."""

    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPORTED = "exported"


class DocumentStatus(StrEnum):
    """One attached file."""

    PENDING = "pending"  # waiting to be read
    PARSED = "parsed"  # text extracted
    UNSUPPORTED = "unsupported"  # .zip, .xls, .doc, ... (recorded, never read)
    FAILED = "failed"  # could not be read (locked, corrupt, expired from the buffer)


class SubmissionState(StrEnum):
    """Where an email or upload is, as the people using the app see it.
    Every change is stored in submission_state_changes with its time."""

    RECEIVED = "received"
    READING = "reading"
    MATCHING = "matching"
    RULE_CHECKS = "rule_checks"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPORTED = "exported"
    IGNORED = "ignored"
    FAILED = "failed"
    REPROCESSING = "reprocessing"


class StepName(StrEnum):
    """One row in the step-by-step log."""

    COLLECT = "collect"
    READ = "read"
    CLASSIFY = "classify"  # optional: is the document a timesheet? (attachment classifier)
    EXTRACT = "extract"
    MATCH = "match"
    RULES = "rules"
    DECIDE = "decide"
    PIPELINE = "pipeline"  # an unexpected error outside one step


class StepResult(StrEnum):
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class TimesheetChange(StrEnum):
    """What turned a timesheet version into the next one (timesheet_versions.change).
    A new version is made by a reprocess or a reviewer's "Create as new version". A
    plain Save edits the current version, and a restore goes back to an existing one;
    approve / reject are in the audit log."""

    ENTRIES_EDITED = "entries_edited"  # days changed, saved as a new version
    EMPLOYEE_MATCHED = "employee_matched"  # only in versions made before saving in place
    WEEK_CHANGED = "week_changed"  # a weekly-total timesheet moved, saved as a new version
    RECALCULATED = "recalculated"  # only in versions made before saving in place
    REPROCESSED = "reprocessed"  # the document was extracted again
    ROLLED_BACK = "rolled_back"  # left when another version was restored


class ReprocessStatus(StrEnum):
    """One reprocess request (see reprocess_runs)."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
