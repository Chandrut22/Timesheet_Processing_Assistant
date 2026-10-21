"""Text -> timesheets: the AI extraction, one call per piece for big sheets."""

import asyncio
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.constants.timesheet_status import StepName, StepResult
from src.control.agents.extraction_agent import extract_timesheets
from src.core.services.activity_log import Stopwatch, record_step
from src.core.services.chunking import Piece, merge_results, split_for_extraction
from src.core.services.document_tables import PersonRows, count_people, missing_rows_flag
from src.data.models import Document, Submission
from src.observability.tracing.spans import pipeline_span
from src.schemas.extraction import ExtractionResult


class _PieceSkipped(Exception):
    """A piece not sent to the AI because another piece of the same document failed."""


@dataclass(slots=True)
class Extraction:
    """What the AI found in one document, and what the next stages need to know."""

    result: ExtractionResult  # at least one timesheet
    text: str  # the document text the AI was given
    truncated: bool  # some piece was longer than LLM_MAX_INPUT_CHARS
    missing_flag: dict[str, object] | None  # people in the tables with no timesheet


async def extract_pieces(
    submission: Submission,
    document: Document,
    pieces: list[Piece],
    parts: list[dict[str, Any]],
) -> ExtractionResult:
    """One AI call per piece, at most CHUNK_PARALLEL at a time, answers merged. If a
    piece fails, the pieces still waiting are skipped and the error is raised as is
    (so it is classified and retried like any extraction failure): no partial set of
    timesheets is ever saved. `parts` collects one line per piece for the step log."""
    gate = asyncio.Semaphore(settings.chunk_parallel)
    failed = asyncio.Event()
    total = len(pieces)

    async def one(number: int, piece: Piece) -> ExtractionResult:
        async with gate:
            if failed.is_set():
                raise _PieceSkipped
            watch = Stopwatch()
            try:
                with pipeline_span(
                    "ai.extract",
                    characters=len(piece.text),
                    truncated=len(piece.text) > settings.llm_max_input_chars,
                    model=settings.llm_model,
                    part=number if total > 1 else None,
                    parts=total if total > 1 else None,
                    people=piece.people or None,
                ) as span:
                    result = await extract_timesheets(
                        document_text=piece.text,
                        filename=document.filename,
                        received_at=submission.received_at,
                        email_subject=submission.subject,
                        email_body=submission.body_text,
                        part=(number, total) if total > 1 else None,
                    )
                    span.set_attribute("timesheets", len(result.timesheets))
            except BaseException:
                failed.set()
                parts.append(
                    {"part": number, "people": piece.people, "ms": watch.ms, "result": "error"}
                )
                raise
            parts.append(
                {
                    "part": number,
                    "people": piece.people,
                    "ms": watch.ms,
                    "timesheets": len(result.timesheets),
                }
            )
            return result

    outcomes = await asyncio.gather(
        *(one(n, p) for n, p in enumerate(pieces, start=1)), return_exceptions=True
    )
    parts.sort(key=lambda p: int(p["part"]))
    errors = [o for o in outcomes if isinstance(o, BaseException)]
    real = [e for e in errors if not isinstance(e, _PieceSkipped)]
    if real or errors:
        raise (real or errors)[0]
    results = [o for o in outcomes if isinstance(o, ExtractionResult)]
    return results[0] if total == 1 else merge_results(results)


async def extract_document(
    session: AsyncSession, submission: Submission, document: Document
) -> Extraction | None:
    """The AI extraction for one document, written to the step log. None = no
    timesheet in it. An AI failure is logged as a step, committed, and raised, so the
    whole submission fails and can be retried or reprocessed."""
    watch = Stopwatch()
    text = document.extracted_text or ""
    # Big sheets are cut into pieces of CHUNK_PEOPLE people (see chunking.py);
    # everything else is one piece, exactly as before.
    pieces = (
        split_for_extraction(
            text,
            people_per_piece=settings.chunk_people,
            above_people=settings.chunk_above_people,
        )
        if settings.chunking_enabled
        else [Piece(text, 0)]
    )
    people = count_people(text)  # None = no table with a name / code column
    parts: list[dict[str, Any]] = []
    step_input = {
        "file": document.filename,
        "characters": len(text),
        "truncated": any(len(p.text) > settings.llm_max_input_chars for p in pieces),
        "people_in_tables": people.total if people is not None else None,
        "parts": len(pieces),
    }
    try:
        result = await extract_pieces(submission, document, pieces, parts)
    except Exception as exc:
        # Usually temporary (model down, timeout): log the step, then let the whole
        # submission fail so it can be retried or reprocessed.
        record_step(
            session,
            submission_id=submission.id,
            document_id=document.id,
            step=StepName.EXTRACT,
            result=StepResult.ERROR,
            message=f"Could not extract timesheet details from {document.filename}: "
            "the AI model did not answer or returned invalid data.",
            input=step_input,
            output={"parts": parts} if len(pieces) > 1 else {},
            error_details=repr(exc),
            duration_ms=watch.ms,
        )
        await session.commit()
        raise

    missing_flag = None
    missing: list[PersonRows] = []
    if people is not None and result.timesheets:
        found = [(t.employee_code, t.employee_name) for t in result.timesheets]
        missing = people.missing(found)
        if missing:
            missing_flag = missing_rows_flag(people, missing)
    counts: dict[str, Any] = {
        "people_in_tables": people.total if people is not None else None,
        "people_missing": len(missing),
    }
    if len(pieces) > 1:
        counts["parts"] = parts

    if not result.timesheets:
        document.error = "No timesheet found in this document."
        record_step(
            session,
            submission_id=submission.id,
            document_id=document.id,
            step=StepName.EXTRACT,
            result=StepResult.WARNING,
            message=f"{document.filename} is not a timesheet",
            input=step_input,
            output={"timesheets": 0, **counts},
            duration_ms=watch.ms,
        )
        return None
    record_step(
        session,
        submission_id=submission.id,
        document_id=document.id,
        step=StepName.EXTRACT,
        result=StepResult.WARNING if missing_flag else StepResult.SUCCESS,
        message=f"Found {len(result.timesheets)} timesheet(s) in {document.filename}"
        + (f" in {len(pieces)} parts" if len(pieces) > 1 else "")
        + (
            f"; {counts['people_missing']} of {people.total} people on the sheet missing"
            if missing_flag and people is not None
            else ""
        ),
        input=step_input,
        output={
            **counts,
            "timesheets": [
                {
                    "employee_name": t.employee_name,
                    "employee_code": t.employee_code,
                    "days": len(t.days),
                    "stated_total": t.stated_total,
                    "confidence": t.confidence,
                }
                for t in result.timesheets
            ],
        },
        duration_ms=watch.ms,
    )
    return Extraction(
        result=result,
        text=text,
        truncated=bool(step_input["truncated"]),
        missing_flag=missing_flag,
    )
