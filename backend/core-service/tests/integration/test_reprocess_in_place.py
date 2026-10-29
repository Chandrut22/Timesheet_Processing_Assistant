"""A reprocess through the real worker pipeline (extraction LLM mocked), on a real
database: timesheets are updated in place (same id, version + 1, the old data in
timesheet_versions), a new person gets a new timesheet, and a person no longer found
is rejected with the removed_by_reprocess flag. Nothing is deleted."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text

from src.constants.roles import RoleName
from src.core.rbac.principal import Principal
from src.core.services import submission_service
from src.core.services.pipeline import extracting
from src.core.services.processing_service import ProcessingService
from src.core.services.review_service import ReviewService
from src.core.services.submission_service import SubmissionService
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import (
    Company,
    Document,
    Employee,
    ReprocessRun,
    Submission,
    Timesheet,
    TimesheetVersion,
)
from src.schemas.extraction import ExtractedDay, ExtractedTimesheet, ExtractionResult

MON = date(2026, 10, 12)
RECEIVED = datetime(2026, 10, 19, 9, tzinfo=UTC)
RITA = Principal(
    id=uuid.uuid4(), role=RoleName.REVIEWER, name="Rita", email="rita@example.com"
)


def person(name: str, code: str, hours: float) -> ExtractedTimesheet:
    return ExtractedTimesheet(
        employee_name=name,
        employee_code=code,
        week_start=MON,
        days=[
            ExtractedDay(work_date=MON + timedelta(days=i), hours=hours)
            for i in range(5)
        ],
        confidence=0.95,
    )


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[dict[str, Any]]:
    answers: list[ExtractionResult] = []

    async def fake_extract(**_: Any) -> ExtractionResult:
        return answers.pop(0)

    async def no_queue(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(extracting, "extract_timesheets", fake_extract)
    monkeypatch.setattr(submission_service, "enqueue_submission", no_queue)
    yield {"answers": answers}
    await engine.dispose()


async def seed() -> uuid.UUID:
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
        s.add_all(
            [
                Employee(company_id=company.id, employee_code=code, full_name=name)
                for code, name in (
                    ("E1", "Grace Hopper"),
                    ("E2", "Hari Prasad"),
                    ("E3", "Priya N"),
                )
            ]
        )
        submission = Submission(
            source="upload", received_at=RECEIVED, company_id=company.id
        )
        s.add(submission)
        await s.flush()
        s.add(
            Document(
                submission_id=submission.id,
                filename="week41.xlsx",
                content_type="application/vnd.ms-excel",
                size_bytes=10,
                sha256="c" * 64,
                status="parsed",
                extracted_text="| Name | Mon | ... |",
            )
        )
        await s.commit()
        return submission.id


async def run(submission_id: uuid.UUID, run_id: uuid.UUID | None = None) -> None:
    async with SessionLocal() as s:
        await ProcessingService(s).process(submission_id, run_id)


async def timesheets(submission_id: uuid.UUID) -> dict[str, Timesheet]:
    async with SessionLocal() as s:
        rows = (
            await s.scalars(
                select(Timesheet).where(Timesheet.submission_id == submission_id)
            )
        ).all()
        return {t.extracted_name or "": t for t in rows}


async def test_a_reprocess_updates_the_same_timesheets(world: dict[str, Any]) -> None:
    answers: list[ExtractionResult] = world["answers"]
    submission_id = await seed()

    answers.append(
        ExtractionResult(
            timesheets=[person("Grace Hopper", "E1", 8), person("Hari Prasad", "E2", 8)]
        )
    )
    await run(submission_id)
    first = await timesheets(submission_id)
    grace, hari = first["Grace Hopper"], first["Hari Prasad"]
    assert (grace.version, hari.version) == (1, 1)
    async with SessionLocal() as s:
        if grace.status != "approved":
            await ReviewService(s).approve(grace.id, None, RITA)

    # The sheet is read again: Grace now 9 h a day, Hari gone, Priya new.
    answers.append(
        ExtractionResult(
            timesheets=[person("Grace Hopper", "E1", 9), person("Priya N", "E3", 7)]
        )
    )
    async with SessionLocal() as s:
        reprocess = await SubmissionService(s).reprocess(
            submission_id, "Sheet was re-sent", RITA, confirm_approved=True
        )
        run_id = reprocess.id
    async with SessionLocal() as s:  # the approval is cleared when the reprocess starts
        assert (await s.get(Timesheet, grace.id)).status == "needs_review"  # type: ignore[union-attr]
    await run(submission_id, run_id)

    after = await timesheets(submission_id)
    assert set(after) == {"Grace Hopper", "Hari Prasad", "Priya N"}  # nothing deleted
    new_grace = after["Grace Hopper"]
    assert new_grace.id == grace.id and new_grace.version == 2
    assert [e.hours for e in new_grace.entries] == [Decimal("9.00")] * 5
    assert new_grace.reprocess_run_id == run_id

    old_hari = after["Hari Prasad"]
    assert old_hari.id == hari.id and old_hari.status == "rejected"
    assert "removed_by_reprocess" in [f["code"] for f in old_hari.flags]
    assert old_hari.version == 1  # a status change, not a data change

    priya = after["Priya N"]
    assert priya.version == 1 and priya.reprocess_run_id == run_id

    async with SessionLocal() as s:
        [saved] = (
            await s.scalars(
                select(TimesheetVersion).where(
                    TimesheetVersion.timesheet_id == grace.id
                )
            )
        ).all()
        assert (saved.version, saved.change, saved.changed_by_name, saved.reason) == (
            1,
            "reprocessed",
            "Rita",
            "Sheet was re-sent",
        )
        assert saved.reprocess_run_id == run_id
        assert [e["hours"] for e in saved.snapshot["entries"]] == [8.0] * 5
        assert (
            saved.snapshot["status"] == "needs_review"
        )  # approval cleared at the start

        finished = await s.get(ReprocessRun, run_id)
        assert finished is not None and finished.status == "completed"
        assert finished.after_result is not None
        assert finished.after_result["replaced"] == {
            str(grace.id): str(grace.id),
            str(hari.id): None,
        }
        assert finished.after_result["removed"] == [str(hari.id)]
        assert {t["name"] for t in finished.after_result["timesheets"]} == {
            "Grace Hopper",
            "Priya N",
        }

        # ... and the reviewer can roll Grace back to what was first extracted.
        restored = await ReviewService(s).restore_version(
            grace.id, 1, "reprocess was wrong", RITA
        )
        assert restored.version == 1  # back on version 1; version 2 is kept
        assert [e.hours for e in restored.entries] == [Decimal("8.00")] * 5


async def test_a_reprocess_that_cannot_be_queued_gives_the_approvals_back(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    answers: list[ExtractionResult] = world["answers"]
    submission_id = await seed()
    answers.append(ExtractionResult(timesheets=[person("Grace Hopper", "E1", 8)]))
    await run(submission_id)
    grace = (await timesheets(submission_id))["Grace Hopper"]
    async with SessionLocal() as s:
        if grace.status != "approved":
            await ReviewService(s).approve(grace.id, None, RITA)
    approved = (await timesheets(submission_id))["Grace Hopper"]

    async def queue_down(*_: Any, **__: Any) -> None:
        raise ConnectionError("redis down")

    monkeypatch.setattr(submission_service, "enqueue_submission", queue_down)
    async with SessionLocal() as s:
        with pytest.raises(ConnectionError):
            await SubmissionService(s).reprocess(
                submission_id, "Sheet was re-sent", RITA, confirm_approved=True
            )
    back = (await timesheets(submission_id))["Grace Hopper"]
    assert back.status == "approved"
    assert back.reviewed_by_name == approved.reviewed_by_name
    assert back.version == 1
