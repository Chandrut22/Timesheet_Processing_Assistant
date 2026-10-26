"""A timesheet the classifier wrongly called "not a timesheet": skipped and logged on
arrival, then extracted by a reprocess (which never asks the classifier). Real
database, real worker pipeline, extraction LLM and classifier mocked."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text

from src.config.settings import settings
from src.constants.roles import RoleName
from src.core.rbac.principal import Principal
from src.core.services import submission_service
from src.core.services.attachment_classifier import ClassifierResult
from src.core.services.pipeline import classifying, extracting
from src.core.services.processing_service import ProcessingService
from src.core.services.submission_service import SubmissionService
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import Company, Document, Employee, Submission, Timesheet
from src.data.models.postgres.activity import ProcessingStep
from src.schemas.extraction import ExtractedDay, ExtractedTimesheet, ExtractionResult

MON = date(2026, 10, 12)
RITA = Principal(id=uuid.uuid4(), role=RoleName.REVIEWER, name="Rita", email="rita@example.com")


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[dict[str, int]]:
    calls = {"classify": 0, "extract": 0}

    async def wrong_classifier(_text: str) -> ClassifierResult:
        calls["classify"] += 1
        return ClassifierResult(label="invoice", p_timesheet=0.04, model="jev-test", duration_ms=5)

    async def fake_extract(**_: Any) -> ExtractionResult:
        calls["extract"] += 1
        return ExtractionResult(
            timesheets=[
                ExtractedTimesheet(
                    employee_name="Grace Hopper",
                    employee_code="E1",
                    week_start=MON,
                    days=[
                        ExtractedDay(work_date=MON + timedelta(days=i), hours=8) for i in range(5)
                    ],
                    confidence=0.95,
                )
            ]
        )

    async def no_queue(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(settings, "classifier_enabled", True)
    monkeypatch.setattr(settings, "classifier_shadow_only", False)
    monkeypatch.setattr(classifying, "classify", wrong_classifier)
    monkeypatch.setattr(extracting, "extract_timesheets", fake_extract)
    monkeypatch.setattr(submission_service, "enqueue_submission", no_queue)
    yield calls
    await engine.dispose()


async def seed() -> tuple[uuid.UUID, uuid.UUID]:
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
        s.add(Employee(company_id=company.id, employee_code="E1", full_name="Grace Hopper"))
        submission = Submission(
            source="upload",
            received_at=datetime(2026, 10, 19, 9, tzinfo=UTC),
            company_id=company.id,
        )
        s.add(submission)
        await s.flush()
        document = Document(
            submission_id=submission.id,
            filename="week41.xlsx",
            content_type="application/vnd.ms-excel",
            size_bytes=10,
            sha256="c" * 64,
            status="parsed",
            extracted_text="| Name | Mon | Tue |\n| Grace Hopper | 8 | 8 |",
        )
        s.add(document)
        await s.commit()
        return submission.id, document.id


async def test_a_wrong_skip_is_fixed_by_a_reprocess(world: dict[str, int]) -> None:
    submission_id, document_id = await seed()
    async with SessionLocal() as s:
        await ProcessingService(s).process(submission_id)

    async with SessionLocal() as s:
        submission = await s.get(Submission, submission_id)
        document = await s.get(Document, document_id)
        assert submission is not None and document is not None
        # Skipped and logged, and the email says why (not "no timesheet found").
        assert submission.state == "ignored"
        assert submission.state_reason == (
            "Not a timesheet (classifier: invoice, 4% timesheet). Reprocess to extract it anyway."
        )
        assert document.error == submission.state_reason
    assert world == {"classify": 1, "extract": 0}

    async with SessionLocal() as s:
        run = await SubmissionService(s).reprocess(submission_id, "Classifier was wrong", RITA)
        run_id = run.id
    async with SessionLocal() as s:
        await ProcessingService(s).process(submission_id, run_id)

    async with SessionLocal() as s:
        submission = await s.get(Submission, submission_id)
        document = await s.get(Document, document_id)
        sheets = (
            await s.scalars(select(Timesheet).where(Timesheet.submission_id == submission_id))
        ).all()
        steps = (
            await s.scalars(
                select(ProcessingStep)
                .where(ProcessingStep.step == "classify")
                .order_by(ProcessingStep.created_at)
            )
        ).all()
        assert submission is not None and document is not None
        assert len(sheets) == 1 and sheets[0].extracted_name == "Grace Hopper"
        assert submission.state != "ignored"  # decided as usual (review or auto-approve)
        assert document.error is None  # the old "not a timesheet" is gone
        assert [x.message for x in steps] == [
            "Not a timesheet (classifier: invoice, 4% timesheet). Not extracted.",
            "Classifier not used: a reprocess always runs the full extraction.",
        ]
    assert world == {"classify": 1, "extract": 1}  # the reprocess never asked it again
