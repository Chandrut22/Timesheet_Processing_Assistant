"""Import every model here. Alembic only sees tables whose model was imported."""

from src.data.models.audit_event import AuditEvent
from src.data.models.base import Base
from src.data.models.company import Company
from src.data.models.document import Document
from src.data.models.employee import Employee
from src.data.models.export_batch import ExportBatch
from src.data.models.holiday import Holiday
from src.data.models.submission import Submission
from src.data.models.timesheet import Timesheet
from src.data.models.timesheet_entry import TimesheetEntry
from src.data.models.whitelist_sender import WhitelistSender

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
    "WhitelistSender",
    "AuditEvent",
]
