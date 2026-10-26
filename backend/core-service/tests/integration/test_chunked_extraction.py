"""A long sheet read in overlapping parts, through the real worker on a real database
(the AI mocked: it reads the rows of the part it is given). Everyone comes out exactly
once, a person read twice in the overlap is one timesheet, a disagreement in the overlap
is flagged, and a failed part is retried on its own; a part that keeps failing saves
nothing."""

import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text

from src.config.settings import settings
from src.core.services.pipeline import extracting
from src.core.services.pipeline.failing import RetryLater
from src.core.services.processing_service import ProcessingService
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import Company, Document, Employee, Submission, Timesheet
from src.data.models.postgres.activity import ProcessingStep
from src.schemas.extraction import ExtractedDay, ExtractedTimesheet, ExtractionResult

MON = date(2026, 10, 12)
PEOPLE = 60
ROW = re.compile(r"^\| (E\d{3}) \| (Person \d{3}) \| (\d+) \| 8 \| 8 \| 8 \| 8 \| 40 \|$", re.M)


def sheet(n: int) -> str:
    lines = [
        "# Lakeside Logistics - week of 2026-10-12",
        "",
        "| Emp ID | Employee Name | Mon | Tue | Wed | Thu | Fri | Total |",
        "|---|---|---|---|---|---|---|---|",
    ]
    lines += [f"| E{i:03d} | Person {i:03d} | 8 | 8 | 8 | 8 | 8 | 40 |" for i in range(1, n + 1)]
    return "\n".join(lines)


class FakeAI:
    """Reads the rows of the part it is given, like the real model would."""

    def __init__(self) -> None:
        self.calls: list[int] = []
        self.fail: dict[int, int] = {}  # part -> failures left
        self.monday_in_part: dict[tuple[int, str], float] = {}  # (part, code) -> Monday hours

    async def __call__(self, **kwargs: Any) -> ExtractionResult:
        part = (kwargs.get("part") or (1, 1))[0]
        self.calls.append(part)
        if self.fail.get(part, 0) > 0:
            self.fail[part] -= 1
            raise TimeoutError("model busy")
        found = []
        for code, name, monday in ROW.findall(kwargs["document_text"]):
            hours = [self.monday_in_part.get((part, code), float(monday))] + [8.0] * 4
            found.append(
                ExtractedTimesheet(
                    employee_code=code,
                    employee_name=name,
                    week_start=MON,
                    days=[
                        ExtractedDay(work_date=MON + timedelta(days=i), hours=h)
                        for i, h in enumerate(hours)
                    ],
                    stated_total=40,
                    confidence=0.95,
                )
            )
        return ExtractionResult(timesheets=found)


@pytest.fixture
async def ai(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FakeAI]:
    fake = FakeAI()
    monkeypatch.setattr(extracting, "extract_timesheets", fake)
    monkeypatch.setattr(extracting, "RETRY_PAUSE_S", 0)
    monkeypatch.setattr(settings, "chunking_enabled", True)
    monkeypatch.setattr(settings, "chunk_people", 15)
    yield fake
    await engine.dispose()


async def seed(n: int = PEOPLE) -> uuid.UUID:
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
            Employee(company_id=company.id, employee_code=f"E{i:03d}", full_name=f"Person {i:03d}")
            for i in range(1, n + 1)
        )
        submission = Submission(
            source="upload",
            received_at=datetime(2026, 10, 19, 9, tzinfo=UTC),
            company_id=company.id,
        )
        s.add(submission)
        await s.flush()
        s.add(
            Document(
                submission_id=submission.id,
                filename="crew.xlsx",
                content_type="application/vnd.ms-excel",
                size_bytes=10,
                sha256="d" * 64,
                status="parsed",
                extracted_text=sheet(n),
            )
        )
        await s.commit()
        return submission.id


async def run(submission_id: uuid.UUID) -> None:
    async with SessionLocal() as s:
        await ProcessingService(s).process(submission_id)


async def timesheets(submission_id: uuid.UUID) -> list[Timesheet]:
    async with SessionLocal() as s:
        rows = await s.scalars(select(Timesheet).where(Timesheet.submission_id == submission_id))
        return list(rows.all())


async def extract_step(submission_id: uuid.UUID) -> ProcessingStep:
    async with SessionLocal() as s:
        step = await s.scalar(
            select(ProcessingStep).where(
                ProcessingStep.submission_id == submission_id, ProcessingStep.step == "extract"
            )
        )
        assert step is not None
        return step


async def test_everyone_once_from_overlapping_parts(ai: FakeAI) -> None:
    submission_id = await seed()
    await run(submission_id)

    sheets = await timesheets(submission_id)
    codes = sorted(t.extracted_code or "" for t in sheets)
    assert codes == [f"E{i:03d}" for i in range(1, PEOPLE + 1)]  # each person exactly once
    assert all(len(t.entries) == 5 for t in sheets)  # no day counted twice
    assert not any(f["code"] == "possible_missing_rows" for t in sheets for f in t.flags)
    assert len(set(ai.calls)) == len(ai.calls) > 1  # one call per part

    step = await extract_step(submission_id)
    assert step.input["parts"] == len(ai.calls)
    assert step.output["joined_across_parts"] > 0  # the overlap rows were read twice
    assert "found in two parts and combined" in step.message


async def test_a_disagreement_in_the_overlap_is_flagged(ai: FakeAI) -> None:
    submission_id = await seed()
    # Find a person in the overlap of parts 1 and 2, and make part 2 read 9 h on Monday.
    pieces = extracting.split_for_extraction(sheet(PEOPLE)).pieces
    both = sorted(set(ROW.findall(pieces[0].text)) & set(ROW.findall(pieces[1].text)))
    code = both[0][0]
    ai.monday_in_part[(2, code)] = 9.0
    await run(submission_id)

    (grace,) = [t for t in await timesheets(submission_id) if t.extracted_code == code]
    monday = [e for e in grace.entries if e.work_date == MON]
    assert [float(e.hours) for e in monday] == [9.0]  # the later part's reading
    flag = next(f for f in grace.flags if f["code"] == "overlap_disagreement")
    assert flag["severity"] == "high" and "part 1" in flag["message"]
    assert grace.status == "needs_review"


async def test_a_failed_part_is_retried_on_its_own(ai: FakeAI) -> None:
    submission_id = await seed()
    ai.fail[2] = 1  # part 2 times out once
    await run(submission_id)

    assert len(await timesheets(submission_id)) == PEOPLE
    assert ai.calls.count(2) == 2 and ai.calls.count(1) == 1  # only part 2 again
    step = await extract_step(submission_id)
    part2 = next(p for p in step.output["parts"] if p["part"] == 2)
    assert part2["attempts"] == 2


async def test_a_part_that_keeps_failing_saves_nothing(ai: FakeAI) -> None:
    submission_id = await seed()
    ai.fail[2] = 99
    with pytest.raises(RetryLater):  # the worker tries the whole job again later
        await run(submission_id)

    assert await timesheets(submission_id) == []
    assert ai.calls.count(2) == 1 + settings.chunk_piece_retries
    async with SessionLocal() as s:
        submission = await s.get(Submission, submission_id)
        assert submission is not None and submission.status != "processed"


async def test_too_many_parts_is_flagged(ai: FakeAI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "chunk_max_parts", 2)
    submission_id = await seed()
    await run(submission_id)

    sheets = await timesheets(submission_id)
    assert 0 < len(sheets) < PEOPLE
    assert all(any(f["code"] == "document_too_large" for f in t.flags) for t in sheets)
