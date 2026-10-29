"""The classifier runs BEFORE any file is read, from the file name and the email only.
An attachment it is sure is not a timesheet is never read nor sent to the AI, its file
is kept, and a reprocess reads it anyway. Real database, real worker pipeline, upload
buffer in a temp folder; the extraction LLM and the classifier are mocked."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text

from src.config.settings import settings
from src.constants.roles import RoleName
from src.core.rbac.principal import Principal
from src.core.services import submission_service
from src.core.services.attachment_classifier import ClassifierError, ClassifierResult
from src.core.services.email_intake_service import BODY_FILENAME
from src.core.services.pipeline import classifying, extracting
from src.core.services.processing_service import ProcessingService
from src.core.services.submission_service import SubmissionService
from src.data.clients import upload_buffer
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import Company, Document, Employee, Submission, Timesheet
from src.data.models.postgres.activity import ProcessingStep
from src.schemas.extraction import ExtractedDay, ExtractedTimesheet, ExtractionResult
from src.schemas.submission import DocumentRead

MON = date(2026, 10, 12)
RITA = Principal(
    id=uuid.uuid4(), role=RoleName.REVIEWER, name="Rita", email="rita@example.com"
)
SHEET = b"Name,Mon,Tue,Wed,Thu,Fri\nGrace Hopper,8,8,8,8,8\n"
NOT_A_TIMESHEET = ClassifierResult(
    label="invoice", p_timesheet=0.04, model="jev-test", duration_ms=5
)
A_TIMESHEET = ClassifierResult(
    label="timesheet", p_timesheet=0.97, model="jev-test", duration_ms=5
)


@dataclass
class World:
    sent: list[str] = field(default_factory=list)  # what the classifier was shown
    extracted: list[str] = field(default_factory=list)  # text the AI was given
    answer: dict[str, ClassifierResult | None] = field(default_factory=dict)


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> AsyncIterator[World]:
    w = World()

    async def fake_classify(sent: str) -> ClassifierResult:
        w.sent.append(sent)
        first = sent.splitlines()[0]
        for name, answer in w.answer.items():
            if first.startswith(f"File: {name}"):
                if answer is None:
                    raise ClassifierError("Classifier call failed: ReadTimeout")
                return answer
        return A_TIMESHEET

    async def fake_extract(**kwargs: Any) -> ExtractionResult:
        w.extracted.append(str(kwargs.get("text", kwargs)))
        return ExtractionResult(
            timesheets=[
                ExtractedTimesheet(
                    employee_name="Grace Hopper",
                    employee_code="E1",
                    week_start=MON,
                    days=[
                        ExtractedDay(work_date=MON + timedelta(days=i), hours=8)
                        for i in range(5)
                    ],
                    confidence=0.95,
                )
            ]
        )

    async def no_queue(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "classifier_enabled", True)
    monkeypatch.setattr(settings, "classifier_shadow_only", False)
    monkeypatch.setattr(settings, "email_refetch_enabled", False)
    monkeypatch.setattr(classifying, "classify", fake_classify)
    monkeypatch.setattr(extracting, "extract_timesheets", fake_extract)
    monkeypatch.setattr(submission_service, "enqueue_submission", no_queue)
    yield w
    await engine.dispose()


async def seed(
    files: list[str], *, source: str = "email", body: str | None = None
) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    """A submission whose files are waiting to be read (bytes in the buffer)."""
    async with SessionLocal() as s:
        await s.execute(
            text("TRUNCATE core.submissions, core.companies, core.audit_events CASCADE")
        )
        company = Company(
            name="Lakeside Logistics",
            hourly_rate=Decimal("450"),
            overtime_rate=Decimal("675"),
            holiday_rate=Decimal("900"),
        )
        s.add(company)
        await s.flush()
        s.add(
            Employee(
                company_id=company.id, employee_code="E1", full_name="Grace Hopper"
            )
        )
        submission = Submission(
            source=source,
            received_at=datetime(2026, 10, 19, 9, tzinfo=UTC),
            company_id=company.id,
            sender_email="payroll@lakeside.example" if source == "email" else None,
            subject="Week 41 hours and the October invoice"
            if source == "email"
            else None,
            body_text=body,
        )
        s.add(submission)
        await s.flush()
        documents: dict[str, Document] = {}
        for name in files:
            if name == BODY_FILENAME:
                assert body is not None
                documents[name] = Document(
                    submission_id=submission.id,
                    filename=name,
                    content_type="text/plain",
                    size_bytes=len(body),
                    sha256="b" * 64,
                    status="parsed",
                    extracted_text=body,
                )
            else:
                documents[name] = Document(
                    submission_id=submission.id,
                    filename=name,
                    content_type="text/csv",
                    size_bytes=len(SHEET),
                    sha256=uuid.uuid4().hex * 2,
                    status="pending",
                )
            s.add(documents[name])
        await s.commit()
        ids = {name: d.id for name, d in documents.items()}
    for name, document_id in ids.items():
        if name != BODY_FILENAME:
            await upload_buffer.put_file(document_id, SHEET)
    return submission.id, ids


async def run(submission_id: uuid.UUID, run_id: uuid.UUID | None = None) -> None:
    async with SessionLocal() as s:
        await ProcessingService(s).process(submission_id, run_id)


async def reprocess(
    submission_id: uuid.UUID, document_id: uuid.UUID | None = None
) -> None:
    async with SessionLocal() as s:
        reprocess_run = await SubmissionService(s).reprocess(
            submission_id, "Classifier was wrong", RITA, document_id=document_id
        )
        run_id = reprocess_run.id
    await run(submission_id, run_id)


async def classify_steps(submission_id: uuid.UUID) -> list[ProcessingStep]:
    async with SessionLocal() as s:
        return list(
            (
                await s.scalars(
                    select(ProcessingStep)
                    .where(
                        ProcessingStep.submission_id == submission_id,
                        ProcessingStep.step.in_(["classify", "read"]),
                    )
                    .order_by(ProcessingStep.created_at)
                )
            ).all()
        )


SKIP_MESSAGE = (
    "Not a timesheet (classifier: invoice, 4% timesheet, from the file name and the "
    "email). Reprocess to read it anyway."
)


async def test_a_wrong_skip_is_never_read_and_a_reprocess_reads_it(
    world: World,
) -> None:
    world.answer["week41.csv"] = NOT_A_TIMESHEET
    submission_id, ids = await seed(["week41.csv"], body="Please find attached.")
    await run(submission_id)

    async with SessionLocal() as s:
        submission = await s.get(Submission, submission_id)
        document = await s.get(Document, ids["week41.csv"])
        assert submission is not None and document is not None
        assert submission.state == "ignored"
        assert submission.state_reason == SKIP_MESSAGE
        # Not read, file kept for a reprocess
        assert document.status == "pending" and document.extracted_text is None
        assert document.error == SKIP_MESSAGE
        assert DocumentRead.model_validate(document).skipped_by_classifier
    assert await upload_buffer.get_file(ids["week41.csv"]) == SHEET
    assert world.extracted == []
    # Only metadata was sent: file name, subject, body; never the sender or the file
    assert world.sent == [
        "File: week41.csv\n"
        "Subject: Week 41 hours and the October invoice\n"
        "Body: Please find attached."
    ]
    steps = await classify_steps(submission_id)
    assert [x.step for x in steps] == ["classify"]  # never read

    await reprocess(submission_id)

    async with SessionLocal() as s:
        submission = await s.get(Submission, submission_id)
        document = await s.get(Document, ids["week41.csv"])
        sheets = (
            await s.scalars(
                select(Timesheet).where(Timesheet.submission_id == submission_id)
            )
        ).all()
        assert submission is not None and document is not None
        assert document.status == "parsed" and document.error is None
        assert "Grace Hopper" in (document.extracted_text or "")
        assert len(sheets) == 1 and submission.state != "ignored"
    assert len(world.sent) == 1  # the reprocess never asked the classifier again
    assert len(world.extracted) == 1
    steps = await classify_steps(submission_id)
    assert [(x.step, x.message) for x in steps][0] == (
        "classify",
        "Not a timesheet (classifier: invoice, 4% timesheet). Not read.",
    )
    assert [x.step for x in steps][1:3] == ["classify", "read"]  # classify, then read
    assert steps[1].message == (
        "Classifier not used: a reprocess always reads the file and runs the full "
        "extraction."
    )


async def test_only_the_invoice_is_left_unread(world: World) -> None:
    world.answer["invoice-oct.csv"] = NOT_A_TIMESHEET
    submission_id, ids = await seed(["invoice-oct.csv", "week41.csv"])
    await run(submission_id)

    async with SessionLocal() as s:
        submission = await s.get(Submission, submission_id)
        invoice = await s.get(Document, ids["invoice-oct.csv"])
        sheet = await s.get(Document, ids["week41.csv"])
        assert submission is not None and invoice is not None and sheet is not None
        assert invoice.status == "pending" and invoice.extracted_text is None
        assert sheet.status == "parsed" and sheet.error is None
        assert submission.state != "ignored"  # the timesheet was processed
    assert len(world.extracted) == 1
    # Each file is judged knowing the other attachments' names
    assert world.sent[0].splitlines()[0] == (
        "File: invoice-oct.csv (1 of 2 attachments; others: week41.csv)"
    )
    assert await upload_buffer.get_file(ids["invoice-oct.csv"]) == SHEET
    assert await upload_buffer.get_file(ids["week41.csv"]) is None  # read: dropped

    # Reprocess just the invoice: it is read now (its file was kept)
    await reprocess(submission_id, ids["invoice-oct.csv"])
    async with SessionLocal() as s:
        invoice = await s.get(Document, ids["invoice-oct.csv"])
        assert invoice is not None and invoice.status == "parsed"


@pytest.mark.parametrize(
    ("answer", "shadow", "message"),
    [
        (None, False, "Classifier unavailable; reading the file as usual."),
        (
            ClassifierResult(
                label="unclear", p_timesheet=0.01, model="j", duration_ms=1
            ),
            False,
            "Classifier: unclear, 1% timesheet. Reading the file.",
        ),
        (
            NOT_A_TIMESHEET,
            True,
            "Shadow mode: would skip (invoice, 4% timesheet); reading anyway.",
        ),
    ],
)
async def test_unsure_failed_or_shadow_always_reads(
    world: World,
    monkeypatch: pytest.MonkeyPatch,
    answer: ClassifierResult | None,
    shadow: bool,
    message: str,
) -> None:
    monkeypatch.setattr(settings, "classifier_shadow_only", shadow)
    world.answer["scan.csv"] = answer
    submission_id, ids = await seed(["scan.csv"])
    await run(submission_id)
    async with SessionLocal() as s:
        document = await s.get(Document, ids["scan.csv"])
        assert document is not None and document.status == "parsed"
    assert len(world.extracted) == 1
    steps = await classify_steps(submission_id)
    assert [(x.step, x.message) for x in steps] == [
        ("classify", message),
        ("read", steps[1].message),
    ]


async def test_uploads_are_never_classified(world: World) -> None:
    world.answer["invoice.csv"] = NOT_A_TIMESHEET
    submission_id, ids = await seed(["invoice.csv"], source="upload")
    await run(submission_id)
    async with SessionLocal() as s:
        document = await s.get(Document, ids["invoice.csv"])
        assert document is not None and document.status == "parsed"
    assert world.sent == [] and len(world.extracted) == 1


async def test_an_email_body_is_judged_from_subject_and_body(world: World) -> None:
    body = "Hi team, the October invoice total is 45,000. Thanks."
    world.answer["none (the email body itself)"] = NOT_A_TIMESHEET
    submission_id, ids = await seed([BODY_FILENAME], body=body)
    await run(submission_id)
    async with SessionLocal() as s:
        submission = await s.get(Submission, submission_id)
        document = await s.get(Document, ids[BODY_FILENAME])
        assert submission is not None and document is not None
        assert submission.state == "ignored"
        assert (document.error or "").startswith("Not a timesheet (classifier:")
    assert world.sent == [
        "File: none (the email body itself)\n"
        "Subject: Week 41 hours and the October invoice\n"
        f"Body: {body}"
    ]
    assert world.extracted == []  # the AI never saw it

    await reprocess(submission_id)
    assert len(world.extracted) == 1 and len(world.sent) == 1
    async with SessionLocal() as s:
        document = await s.get(Document, ids[BODY_FILENAME])
        assert document is not None and document.error is None


async def test_a_retry_does_not_ask_again(world: World) -> None:
    world.answer["invoice.csv"] = NOT_A_TIMESHEET
    submission_id, _ = await seed(["invoice.csv"])
    await run(submission_id)
    await run(submission_id)  # e.g. the job runs again after a worker restart
    assert len(world.sent) == 1 and world.extracted == []
