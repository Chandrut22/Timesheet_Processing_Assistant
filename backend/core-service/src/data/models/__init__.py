"""Import every model here. Alembic only sees tables whose model was imported."""

from src.data.models.postgres.activity import ProcessingStep, SubmissionStateChange
from src.data.models.postgres.audit_event import AuditEvent
from src.data.models.postgres.base import Base
from src.data.models.postgres.company import Company
from src.data.models.postgres.document import Document
from src.data.models.postgres.employee import Employee
from src.data.models.postgres.export_batch import ExportBatch
from src.data.models.postgres.holiday import Holiday
from src.data.models.postgres.reprocess_run import ReprocessRun
from src.data.models.postgres.submission import Submission
from src.data.models.postgres.timesheet import Timesheet
from src.data.models.postgres.timesheet_entry import TimesheetEntry
from src.data.models.postgres.timesheet_version import TimesheetVersion
from src.data.models.postgres.whitelist_sender import WhitelistSender

__all__ = [
    "Base",
    "Company",
    "Document",
    "Employee",
    "ExportBatch",
    "Holiday",
    "Submission",
    "Timesheet",
    "TimesheetEntry",
    "TimesheetVersion",
    "WhitelistSender",
    "AuditEvent",
    "ProcessingStep",
    "ReprocessRun",
    "SubmissionStateChange",
]
