"""A photo through the whole worker pipeline (claim, read, extract, match, decide) on a
real database, with the vision model and the extraction LLM mocked: handwritten hours
always end in needs_review, even when everything matches; a printed scan does not."""

import io
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from PIL import Image
from sqlalchemy import select, text

from src.config.settings import settings
from src.core.services.documents import document_reader
from src.core.services.documents.document_limits import ReadLimit
from src.core.services.pipeline import extracting
from src.core.services.processing_service import ProcessingService
from src.data.clients import upload_buffer
from src.data.clients.postgres import SessionLocal, engine
from src.data.models import Company, Document, Employee, Submission, Timesheet
from src.handlers.http_clients import vision_reader
from src.schemas.extraction import ExtractedDay, ExtractedTimesheet, ExtractionResult

RECEIVED = datetime(2026, 10, 19, 9, tzinfo=UTC)  # Monday
WEEK = date(2026, 10, 12)
TRANSCRIPT = (
    "Name: Grace Hopper\n| Day | Hours |\n|---|---|\n| Mon | 8 |\n| Tue | [UNCLEAR] |"
)


def vision_answer(
    transcription: str, classification: str = "mixed", by_hand: bool = True
) -> str:
    return json.dumps(
        {
            "classification": classification,
            "confidence": 0.93,
            "has_handwriting": by_hand,
            "has_handwritten_hours": by_hand,
            "has_printed_text": True,
            "reason": "Printed table, hours in pen" if by_hand else "All printed",
            "transcription": transcription,
        }
    )


@dataclass
class Reply:
    content: str


class FakeVisionModel:
    def __init__(self) -> None:
        self.calls = 0
        self.reply = vision_answer(TRANSCRIPT)

    def invoke(self, messages: list[dict[str, Any]]) -> Reply:
        self.calls += 1
        return Reply(self.reply)


def photo() -> bytes:
    out = io.BytesIO()
    Image.effect_noise((1200, 1600), 60).convert("RGB").save(
        out, format="JPEG", quality=90
    )
    return out.getvalue()


def sheet(unreadable: list[str]) -> ExtractionResult:
    days = [
        ExtractedDay(work_date=WEEK + timedelta(days=i), hours=8)
        for i in range(5)
        if (WEEK + timedelta(days=i)).isoformat() not in unreadable
    ]
    return ExtractionResult(
        timesheets=[
            ExtractedTimesheet(
                employee_name="Grace Hopper",
                week_start=WEEK,
                days=days,
                stated_total=8 * len(days) if not unreadable else None,
                unreadable_days=unreadable,
                confidence=0.99,
            )
        ]
    )


@pytest.fixture
async def world(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> AsyncIterator[dict[str, Any]]:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "vision_base_url", "https://ollama.com/v1")
    monkeypatch.setattr(settings, "vision_model", "gemma4:31b-cloud")
    model = FakeVisionModel()
    monkeypatch.setattr(vision_reader, "_default_model", lambda: model)
    yield {"model": model, "monkeypatch": monkeypatch}
    await engine.dispose()


async def seed(data: bytes) -> tuple[uuid.UUID, uuid.UUID]:
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
                company_id=company.id, employee_code="E001", full_name="Grace Hopper"
            )
        )
        submission = Submission(
            source="upload", received_at=RECEIVED, company_id=company.id
        )
        s.add(submission)
        await s.flush()
        document = Document(
            submission_id=submission.id,
            filename="grace.jpg",
            content_type="image/jpeg",
            size_bytes=len(data),
            sha256="b" * 64,
        )
        s.add(document)
        await s.commit()
        await upload_buffer.put_file(document.id, data)
        return submission.id, document.id


async def run(submission_id: uuid.UUID) -> None:
    async with SessionLocal() as s:
        await ProcessingService(s).process(submission_id)


async def results(document_id: uuid.UUID) -> tuple[Document, list[Timesheet]]:
    async with SessionLocal() as s:
        document = await s.get(Document, document_id)
        assert document is not None
        sheets = (
            await s.scalars(
                select(Timesheet).where(Timesheet.document_id == document_id)
            )
        ).all()
        return document, list(sheets)


def codes(ts: Timesheet) -> list[str]:
    return [f["code"] for f in ts.flags or []]


async def test_a_handwritten_photo_ends_in_review_with_the_new_flags(
    world: dict[str, Any],
) -> None:
    mp: pytest.MonkeyPatch = world["monkeypatch"]
    mp.setattr(settings, "vision_enabled", True)
    seen: list[str] = []

    async def fake_extract(**kwargs: Any) -> ExtractionResult:
        seen.append(kwargs["document_text"])
        return sheet(unreadable=["2026-10-13"])

    mp.setattr(extracting, "extract_timesheets", fake_extract)
    submission_id, document_id = await seed(photo())
    await run(submission_id)

    document, [ts] = await results(document_id)
    assert world["model"].calls == 1
    assert seen == [TRANSCRIPT]  # the vision transcript, not OCR, was extracted
    assert (document.read_method, document.unclear_marks) == ("vision", 1)
    assert (document.writing_class, document.has_handwritten_hours) == ("mixed", True)
    assert ts.status == "needs_review"
    assert {"handwritten_hours", "unreadable_values"} <= set(codes(ts))
    assert "2026-10-13" in next(
        f["message"] for f in ts.flags if f["code"] == "unreadable_values"
    )
    assert date(2026, 10, 13) not in {e.work_date for e in ts.entries}  # never 0 hours


async def test_handwritten_hours_are_never_auto_approved_but_a_printed_scan_can_be(
    world: dict[str, Any],
) -> None:
    mp: pytest.MonkeyPatch = world["monkeypatch"]

    async def perfect(**kwargs: Any) -> ExtractionResult:
        return sheet(unreadable=[])

    mp.setattr(extracting, "extract_timesheets", perfect)

    # Control: the same sheet read as a typed document is approved automatically.
    mp.setattr(settings, "vision_enabled", False)
    mp.setattr(document_reader, "_read_with_docling", lambda *a, **k: _typed())
    submission_id, document_id = await seed(photo())
    await run(submission_id)
    document, [typed] = await results(document_id)
    assert document.read_method == "docling"
    control_approved = typed.status == "approved"

    mp.setattr(settings, "vision_enabled", True)
    readable = TRANSCRIPT.replace("[UNCLEAR]", "8")  # every value readable
    world["model"].reply = vision_answer(readable)  # ... but the hours are in pen
    submission_id, document_id = await seed(photo())
    await run(submission_id)
    document, [ts] = await results(document_id)
    assert (document.read_method, document.unclear_marks) == ("vision", 0)
    assert "unreadable_values" not in codes(ts)
    assert ts.status == "needs_review"
    assert "handwritten_hours" in codes(ts)

    # A clearly printed scan read by the vision model keeps the normal rules.
    world["model"].reply = vision_answer(readable, "printed_only", by_hand=False)
    submission_id, document_id = await seed(photo())
    await run(submission_id)
    document, [printed] = await results(document_id)
    assert document.writing_class == "printed_only"
    assert printed.status == "approved", codes(printed)
    assert control_approved, f"control should auto-approve; flags: {codes(typed)}"


def _typed() -> tuple[str, ReadLimit]:
    return TRANSCRIPT.replace("[UNCLEAR]", "8"), ReadLimit()
