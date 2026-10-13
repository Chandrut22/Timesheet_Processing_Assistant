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
