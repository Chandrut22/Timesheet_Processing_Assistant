"""Test case 8: an email with a corrupted attachment, in the middle of a batch, through
the real worker on a real database (the extraction LLM mocked). The damaged and the
password-protected files fail with a clear message logged against the Read step, the
good attachment is still read and extracted, an email with only a damaged file ends
Failed, and the next email in the batch is processed normally."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text

from src.config.settings import settings
from src.core.services.pipeline import extracting
from src.core.services.processing_service import ProcessingService
from src.data.clients import upload_buffer
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import Company, Document, Employee, Submission, Timesheet
from src.data.models.postgres.activity import ProcessingStep
from src.schemas.extraction import ExtractedDay, ExtractedTimesheet, ExtractionResult
from tests.fixtures.pdfs import encrypted_pdf

RECEIVED = datetime(2026, 10, 19, 9, tzinfo=UTC)
WEEK = date(2026, 10, 12)
GOOD_CSV = b"name,date,hours\nGrace Hopper,2026-10-12,8\nGrace Hopper,2026-10-13,8\n"
BROKEN_PDF = b"%PDF-1.7 corrupted in transit" * 200


def locked_pdf() -> bytes:
    return encrypted_pdf(user="secret", owner="owner")


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> AsyncIterator[list[str]]:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    # Vision on, as on the machine where the crash was seen: a damaged PDF has no text
    # layer, so it used to be sent to the vision reader, which crashed in PDFium.
    monkeypatch.setattr(settings, "vision_enabled", True)
    monkeypatch.setattr(settings, "vision_base_url", "https://example.invalid/v1")
    monkeypatch.setattr(settings, "vision_model", "m")
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

    monkeypatch.setattr(extracting, "extract_timesheets", fake_extract)
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
    yield extracted
    await engine.dispose()


async def email(files: list[tuple[str, bytes]]) -> uuid.UUID:
    async with SessionLocal() as s:
        company_id = await s.scalar(select(Company.id))
        submission = Submission(
            source="email",
            received_at=RECEIVED,
            company_id=company_id,
            sender_email="payroll@lakeside.example",
            subject="Timesheets",
        )
        s.add(submission)
        await s.flush()
        documents = [
            Document(
                submission_id=submission.id,
                filename=name,
                content_type="application/octet-stream",
                size_bytes=len(data),
                sha256=uuid.uuid4().hex * 2,
            )
            for name, data in files
        ]
        s.add_all(documents)
        await s.commit()
        for document, (_, data) in zip(documents, files, strict=True):
            await upload_buffer.put_file(document.id, data)
        return submission.id


async def run(submission_id: uuid.UUID) -> None:
    async with SessionLocal() as s:
        await ProcessingService(s).process(submission_id)  # never raises for a bad file


async def test_a_corrupted_attachment_in_the_middle_of_a_batch(world: list[str]) -> None:
    batch = [
        await email([("grace.csv", GOOD_CSV)]),
        await email([("broken.pdf", BROKEN_PDF)]),  # only a damaged file
        await email([("grace.csv", GOOD_CSV), ("locked.pdf", locked_pdf())]),
        await email([("grace.csv", GOOD_CSV)]),  # after the bad ones
    ]
    for submission_id in batch:
        await run(submission_id)

    async with SessionLocal() as s:
        states = [(await s.get(Submission, i)).state for i in batch]  # type: ignore[union-attr]
        assert states[1] == "failed"
        # before and after: processed normally (the later ones are flagged as duplicates)
        assert "failed" not in (states[0], states[3])
        assert states[2] != "failed"  # its good attachment made a timesheet

        broken = await s.scalar(select(Document).where(Document.submission_id == batch[1]))
        assert broken is not None and broken.status == "failed"
        assert broken.error == (
            "'broken.pdf' is damaged or not a valid file. Ask the sender to resend it."
        )
        locked = await s.scalar(select(Document).where(Document.filename == "locked.pdf"))
        assert locked is not None and locked.status == "failed"
        assert "password-protected" in (locked.error or "")

        failure = (await s.get(Submission, batch[1])).state_reason  # type: ignore[union-attr]
        assert failure == broken.error  # the email says why

        steps = (
            await s.scalars(
                select(ProcessingStep).where(
                    ProcessingStep.document_id.in_([broken.id, locked.id]),
                    ProcessingStep.step == "read",
                )
            )
        ).all()
        assert sorted((st.result, st.message) for st in steps) == sorted(
            [("error", broken.error), ("error", locked.error)]
        )
        assert all(st.error_details for st in steps)  # the technical text, for the log

        sheets = (await s.scalars(select(Timesheet.submission_id))).all()
        assert sorted(sheets) == sorted([batch[0], batch[2], batch[3]])
    assert len(world) == 3  # the good files were extracted; the bad ones never reached it
