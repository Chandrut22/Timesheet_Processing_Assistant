"""Reprocess fetches the email again from the mailbox when its files are gone, through
the real worker on a real database (the mailbox and the extraction LLM are faked).

A failed attachment, an ignored email (once the sender is whitelisted) and refetch=true
read the original email again in the SAME submission; an email no longer in the
mailbox, another sender's email, an upload, or a mail server that is down each end the
way a reviewer can act on."""

import hashlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from email.message import EmailMessage, Message
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import select, text

from src.config.settings import settings
from src.constants.roles import RoleName
from src.core.exceptions import ConflictError
from src.core.rbac.principal import Principal
from src.core.services import submission_service
from src.core.services.email_intake_service import IGNORED_NOT_READ
from src.core.services.pipeline import extracting, fetching
from src.core.services.pipeline.failing import RetryLater
from src.core.services.processing_service import ProcessingService
from src.core.services.submission_service import SubmissionService
from src.data.clients import upload_buffer
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import Company, Document, Employee, Submission, Timesheet, WhitelistSender
from src.data.models.postgres.activity import ProcessingStep
from src.handlers.email.imap_source import MailConnectionLost
from src.schemas.extraction import ExtractedDay, ExtractedTimesheet, ExtractionResult

RECEIVED = datetime(2026, 10, 19, 9, tzinfo=UTC)
WEEK = date(2026, 10, 12)
SENDER = "payroll@lakeside.example"
MID = "<week41-abc@lakeside.example>"
CSV = b"name,date,hours\nGrace Hopper,2026-10-12,8\nGrace Hopper,2026-10-13,8\n"
RITA = Principal(id=uuid.uuid4(), role=RoleName.REVIEWER, name="Rita", email="rita@example.com")


def original(files: list[tuple[str, bytes]], sender: str = SENDER) -> Message:
    m = EmailMessage()
    m["From"] = sender
    m["To"] = "timesheets@example.com"
    m["Subject"] = "Timesheets week 41"
    m["Message-ID"] = MID
    m["Date"] = "Mon, 19 Oct 2026 09:00:00 +0000"
    m.set_content("Hi, the hours for week 41 are attached. Thanks, Payroll")
    for name, data in files:
        m.add_attachment(data, maintype="application", subtype="octet-stream", filename=name)
    return m


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> AsyncIterator[dict[str, Any]]:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "imap_host", "imap.example.com")
    monkeypatch.setattr(settings, "imap_user", "timesheets@example.com")
    monkeypatch.setattr(settings, "imap_password", SecretStr("app-password"))
    monkeypatch.setattr(settings, "email_require_sender_auth", False)
    monkeypatch.setattr(settings, "email_refetch_enabled", True)
    mailbox: dict[str, Any] = {"message": None, "searched": [], "error": None}

    def fake_find(message_id: str) -> Message | None:
        mailbox["searched"].append(message_id)
        if mailbox["error"] is not None:
            raise mailbox["error"]
        found: Message | None = mailbox["message"]
        return found

    extracted: list[str] = []

    async def fake_extract(**kwargs: Any) -> ExtractionResult:
        extracted.append(kwargs["document_text"])
        return ExtractionResult(
            timesheets=[
                ExtractedTimesheet(
                    employee_name="Grace Hopper",
                    week_start=WEEK,
                    days=[
                        ExtractedDay(work_date=WEEK + timedelta(days=i), hours=8) for i in range(2)
                    ],
                    confidence=0.95,
                )
            ]
        )

    async def no_queue(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(fetching, "_find", fake_find)
    monkeypatch.setattr(extracting, "extract_timesheets", fake_extract)
    monkeypatch.setattr(submission_service, "enqueue_submission", no_queue)
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
        s.add(Employee(company_id=company.id, employee_code="E001", full_name="Grace Hopper"))
        await s.commit()
        mailbox["company_id"] = company.id
    mailbox["extracted"] = extracted
    yield mailbox
    await engine.dispose()


async def whitelist(company_id: uuid.UUID) -> None:
    async with SessionLocal() as s:
        s.add(WhitelistSender(company_id=company_id, kind="email", value=SENDER))
        await s.commit()


async def saved_email(
    world: dict[str, Any],
    *,
    status: str = "processed",
    doc_status: str = "failed",
    doc_error: str | None = "The file expired before it was processed.",
    source: str = "email",
) -> uuid.UUID:
    async with SessionLocal() as s:
        submission = Submission(
            source=source,
            status=status,
            state="failed" if status == "processed" else status,
            company_id=world["company_id"] if status != "ignored" else None,
            sender_email=SENDER if source == "email" else None,
            subject="Timesheets week 41",
            message_id=MID if source == "email" else None,
            received_at=RECEIVED,
            processed_at=RECEIVED if status == "processed" else None,
        )
        s.add(submission)
        await s.flush()
        s.add(
            Document(
                submission_id=submission.id,
                filename="grace.csv",
                content_type="text/csv",
                size_bytes=len(CSV),
                sha256=hashlib.sha256(CSV).hexdigest(),
                status=doc_status,
                error=doc_error,
                extracted_text="name,date,hours\nold text" if doc_status == "parsed" else None,
            )
        )
        await s.commit()
        return submission.id


async def reprocess(submission_id: uuid.UUID, **kwargs: Any) -> uuid.UUID:
    async with SessionLocal() as s:
        run = await SubmissionService(s).reprocess(submission_id, "Fix the file", RITA, **kwargs)
        return run.id


async def work(submission_id: uuid.UUID, run_id: uuid.UUID) -> None:
    async with SessionLocal() as s:
        await ProcessingService(s).process(submission_id, run_id)


async def state(submission_id: uuid.UUID) -> dict[str, Any]:
    async with SessionLocal() as s:
        submission = await s.get(Submission, submission_id)
        assert submission is not None
        documents = (
            await s.scalars(select(Document).where(Document.submission_id == submission_id))
        ).all()
        steps = (
            await s.scalars(
                select(ProcessingStep)
                .where(
                    ProcessingStep.submission_id == submission_id, ProcessingStep.step == "fetch"
                )
                .order_by(ProcessingStep.created_at)
            )
        ).all()
        timesheets = (
            await s.scalars(select(Timesheet).where(Timesheet.submission_id == submission_id))
        ).all()
        return {
            "submission": submission,
            "documents": {d.filename: d for d in documents},
            "fetch_steps": steps,
            "timesheets": timesheets,
        }


async def test_a_failed_attachment_is_fetched_from_the_mailbox(world: dict[str, Any]) -> None:
    world["message"] = original([("grace.csv", CSV)])
    submission_id = await saved_email(world)
    async with SessionLocal() as s:
        document_id = await s.scalar(select(Document.id))

    run_id = await reprocess(submission_id)
    await work(submission_id, run_id)

    after = await state(submission_id)
    assert world["searched"] == [MID]
    document = after["documents"]["grace.csv"]
    assert document.id == document_id  # the same document: no duplicate-file flag on itself
    assert document.status == "parsed"
    assert "Grace Hopper" in (document.extracted_text or "")
    assert len(after["timesheets"]) == 1
    assert not any(f["code"] == "duplicate_file" for f in after["timesheets"][0].flags)
    (step,) = after["fetch_steps"]
    assert step.result == "success"
    assert step.output["fetched"] == ["grace.csv"]
    assert step.reprocess_run_id == run_id
    assert await upload_buffer.get_file(document_id) is None  # read, so the bytes are gone
    async with SessionLocal() as s:
        from src.data.models import ReprocessRun

        run = await s.get(ReprocessRun, run_id)
        assert run is not None and run.refetch == "missing" and run.status == "completed"


async def test_an_ignored_email_is_processed_once_the_sender_is_whitelisted(
    world: dict[str, Any],
) -> None:
    world["message"] = original([("grace.csv", CSV)])
    submission_id = await saved_email(
        world, status="ignored", doc_status="unsupported", doc_error=IGNORED_NOT_READ
    )

    with pytest.raises(ConflictError, match="still not on any company's whitelist"):
        await reprocess(submission_id)
    assert world["searched"] == []

    await whitelist(world["company_id"])
    run_id = await reprocess(submission_id)
    await work(submission_id, run_id)

    after = await state(submission_id)
    assert after["submission"].company_id == world["company_id"]
    assert after["submission"].body_text  # the text dropped on arrival is kept now
    assert after["documents"]["grace.csv"].status == "parsed"
    assert len(after["timesheets"]) == 1
    assert after["submission"].state != "ignored"


async def test_an_email_no_longer_in_the_mailbox_fails_with_what_to_do(
    world: dict[str, Any],
) -> None:
    world["message"] = None
    submission_id = await saved_email(world)

    run_id = await reprocess(submission_id)
    await work(submission_id, run_id)

    after = await state(submission_id)
    document = after["documents"]["grace.csv"]
    assert document.status == "failed"
    assert "no longer in the mailbox" in (document.error or "")
    assert "Ask the sender to send it again" in (document.error or "")
    assert after["fetch_steps"][0].result == "error"
    assert after["submission"].state == "failed"


async def test_an_email_from_another_sender_is_not_used(world: dict[str, Any]) -> None:
    world["message"] = original([("grace.csv", CSV)], sender="someone@else.example")
    submission_id = await saved_email(world)

    run_id = await reprocess(submission_id)
    await work(submission_id, run_id)

    after = await state(submission_id)
    assert after["documents"]["grace.csv"].status == "failed"
    assert "someone@else.example" in (after["documents"]["grace.csv"].error or "")
    assert after["timesheets"] == []


async def test_a_new_attachment_in_the_original_is_added(world: dict[str, Any]) -> None:
    other = b"name,date,hours\nGrace Hopper,2026-10-14,8\n"
    world["message"] = original([("grace.csv", CSV), ("extra.csv", other)])
    submission_id = await saved_email(world)

    run_id = await reprocess(submission_id)
    await work(submission_id, run_id)

    after = await state(submission_id)
    assert set(after["documents"]) == {"grace.csv", "extra.csv"}
    assert after["fetch_steps"][0].output["added"] == ["extra.csv"]
    assert all(d.status == "parsed" for d in after["documents"].values())


async def test_saved_text_is_used_unless_refetch_is_asked(world: dict[str, Any]) -> None:
    world["message"] = original([("grace.csv", CSV)])
    submission_id = await saved_email(world, doc_status="parsed", doc_error=None)

    run_id = await reprocess(submission_id)  # the text is saved: no mailbox needed
    await work(submission_id, run_id)
    assert world["searched"] == []
    assert world["extracted"] == ["name,date,hours\nold text"]

    # Read the original again (the timesheet was auto-approved: confirm replacing it).
    run_id = await reprocess(submission_id, refetch=True, confirm_approved=True)
    await work(submission_id, run_id)
    assert world["searched"] == [MID]
    after = await state(submission_id)
    assert "Grace Hopper" in (after["documents"]["grace.csv"].extracted_text or "")
    assert "Grace Hopper" in world["extracted"][-1]


async def test_refetch_false_keeps_the_old_answer(world: dict[str, Any]) -> None:
    submission_id = await saved_email(world)
    with pytest.raises(ConflictError, match="no longer stored"):
        await reprocess(submission_id, refetch=False)
    assert world["searched"] == []


async def test_an_upload_is_never_fetched(world: dict[str, Any]) -> None:
    submission_id = await saved_email(world, source="upload")
    with pytest.raises(ConflictError, match="upload the file again"):
        await reprocess(submission_id)
    with pytest.raises(ConflictError, match="upload has no copy in the mailbox"):
        await reprocess(submission_id, refetch=True)
    assert world["searched"] == []


async def test_turned_off_it_says_to_ask_the_sender(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "email_refetch_enabled", False)
    submission_id = await saved_email(world)
    with pytest.raises(ConflictError, match="EMAIL_REFETCH_ENABLED"):
        await reprocess(submission_id)


async def test_a_mail_server_that_is_down_is_tried_again_later(world: dict[str, Any]) -> None:
    world["error"] = MailConnectionLost("TimeoutError: timed out")
    submission_id = await saved_email(world)
    run_id = await reprocess(submission_id)

    with pytest.raises(RetryLater):
        await work(submission_id, run_id)

    after = await state(submission_id)
    assert after["submission"].retry_at is not None
    assert "mail server could not be reached" in (after["submission"].error or "")

    world["error"] = None  # the server is back: the scheduled run fetches it
    world["message"] = original([("grace.csv", CSV)])
    async with SessionLocal() as s:
        submission = await s.get(Submission, submission_id)
        assert submission is not None
        token = submission.retry_token
    async with SessionLocal() as s:
        await ProcessingService(s).process(submission_id, run_id, token)
    after = await state(submission_id)
    assert after["documents"]["grace.csv"].status == "parsed"
    assert len(after["timesheets"]) == 1
