"""Text -> timesheets: the AI extraction, one call per piece for long documents.

A long document is cut into overlapping pieces (chunking.py), each piece is sent to the
AI on its own (at most CHUNK_PARALLEL at a time, a failed piece retried on its own), and
the answers are combined: the same person and week from two pieces become one
timesheet. Matching and the pay rules then run once, on the combined timesheets."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.constants.timesheet_status import StepName, StepResult
from src.control.agents.extraction_agent import extract_timesheets
from src.core.services.activity_log import Stopwatch, record_step
from src.core.services.chunking import (
    Combined,
    Piece,
    Split,
    merge_results,
    single_piece,
)
from src.core.services.chunking import split_with_overlap as split_document
from src.core.services.document_tables import (
    PersonRows,
    count_people,
    missing_rows_flag,
)
from src.core.services.failures import AnswerTooLongError
from src.core.services.timesheet_builder import truncation_flag
from src.data.models import Document, Submission
from src.observability.metrics.instruments import timesheets_extracted
from src.observability.tracing.spans import pipeline_span
from src.schemas.extraction import ExtractionResult

logger = logging.getLogger(__name__)
RETRY_PAUSE_S = (
    1.0  # between attempts of one piece (a dropped connection, a busy model)
)


class _PieceSkippedError(Exception):
    """A piece not sent to the AI because another piece of the same document failed."""


@dataclass(slots=True)
class Extraction:
    """What the AI found in one document, and what the next stages need to know."""

    combined: Combined  # at least one timesheet; with the parts each came from
    text: str  # the document text the AI was given
    parts: int  # pieces the document was read in (1 = read whole)
    missing_flag: dict[str, object] | None  # people in the tables with no timesheet
    size_flags: list[dict[str, Any]] = field(
        default_factory=list
    )  # truncated / too large

    @property
    def result(self) -> ExtractionResult:
        return self.combined.result


def split_for_extraction(text: str) -> Split:
    """The pieces this document is read in (one piece when chunking is off or it is
    short)."""
    if not settings.chunking_enabled:
        return single_piece(text)
    return split_document(
        text,
        target=settings.chunk_target_chars,
        overlap=settings.chunk_overlap_chars,
        max_parts=settings.chunk_max_parts,
        max_people=settings.chunk_people,
    )


def size_flags(split: Split) -> list[dict[str, Any]]:
    """Never a silent cut: say when the AI did not see all of the document."""
    flags: list[dict[str, Any]] = []
    limit = settings.llm_max_input_chars
    if len(split.pieces) == 1:
        flag = truncation_flag(
            split.pieces[0].text
        )  # one piece longer than the AI reads
        if flag is not None:
            flags.append(flag)
    else:
        long_parts = [
            n for n, p in enumerate(split.pieces, start=1) if len(p.text) > limit
        ]
        if long_parts:
            flags.append(
                {
                    "code": "document_truncated",
                    "message": f"Part(s) {', '.join(map(str, long_parts))} of this "
                    f"long document had a single block longer than {limit:,} "
                    "characters; only the start of it was read. Check the original.",
                    "parts": long_parts,
                }
            )
    if split.capped:
        flags.append(
            {
                "code": "document_too_large",
                "message": f"The document is too long ({split.total_chars:,} "
                f"characters): it was read in {len(split.pieces)} parts (the most "
                f"allowed), up to line {split.stopped_at_line}. Hours after that are "
                "missing. Split the file and send it again.",
                "characters": split.total_chars,
                "read_characters": split.read_chars,
                "stopped_at_line": split.stopped_at_line,
            }
        )
    return flags


async def extract_pieces(
    submission: Submission,
    document: Document,
    pieces: list[Piece],
    parts: list[dict[str, Any]],
) -> Combined:
    """One AI call per piece, at most CHUNK_PARALLEL at a time, answers combined.

    A failed piece (of a document read in parts) is tried again on its own, up to
    CHUNK_PIECE_RETRIES more times; the pieces that worked are kept. If a piece still
    fails, the pieces still waiting are skipped and the error is raised as is (so it is
    classified and retried like any extraction failure): no partial set of timesheets is
    ever saved. `parts` collects one line per piece for the step log."""
    gate = asyncio.Semaphore(settings.chunk_parallel)
    failed = asyncio.Event()
    total = len(pieces)
    retries = settings.chunk_piece_retries if total > 1 else 0

    async def call(number: int, piece: Piece) -> ExtractionResult:
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
            return result

    async def one(number: int, piece: Piece) -> ExtractionResult:
        async with gate:
            watch = Stopwatch()
            line: dict[str, Any] = {
                "part": number,
                "characters": len(piece.text),
                "overlap_characters": piece.overlap_chars,
                "lines": [piece.first_line + 1, piece.end_line],
                "people": piece.people,
            }
            attempt = 0
            while True:
                if failed.is_set():
                    raise _PieceSkippedError
                attempt += 1
                try:
                    result = await call(number, piece)
                    break
                except AnswerTooLongError:
                    failed.set()  # a retry gives the same long answer
                    parts.append(
                        {**line, "attempts": attempt, "ms": watch.ms, "result": "error"}
                    )
                    raise
                except Exception as exc:
                    if attempt > retries:
                        failed.set()
                        parts.append(
                            {
                                **line,
                                "attempts": attempt,
                                "ms": watch.ms,
                                "result": "error",
                            }
                        )
                        raise
                    logger.warning(
                        "Part %d of %d failed (attempt %d), trying it again: %s",
                        number,
                        total,
                        attempt,
                        type(exc).__name__,
                    )
                    await asyncio.sleep(RETRY_PAUSE_S)
            parts.append(
                {
                    **line,
                    "attempts": attempt,
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
    real = [e for e in errors if not isinstance(e, _PieceSkippedError)]
    if real or errors:
        raise (real or errors)[0]
    results = [o for o in outcomes if isinstance(o, ExtractionResult)]
    return Combined.of(results[0]) if total == 1 else merge_results(results)


async def extract_document(
    session: AsyncSession, submission: Submission, document: Document
) -> Extraction | None:
    """The AI extraction for one document, written to the step log. None = no
    timesheet in it. An AI failure is logged as a step, committed, and raised, so the
    whole submission fails and can be retried or reprocessed."""
    watch = Stopwatch()
    text = document.extracted_text or ""
    split = split_for_extraction(text)  # long documents: overlapping pieces
    pieces = split.pieces
    people = count_people(text)  # None = no table with a name / code column
    parts: list[dict[str, Any]] = []
    step_input = {
        "file": document.filename,
        "characters": len(text),
        "truncated": any(len(p.text) > settings.llm_max_input_chars for p in pieces),
        "people_in_tables": people.total if people is not None else None,
        "parts": len(pieces),
        "read_characters": split.read_chars,
    }
    try:
        combined = await extract_pieces(submission, document, pieces, parts)
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
    result = combined.result
    flags = size_flags(split)

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
        counts["joined_across_parts"] = combined.joined
        counts["overlap_disagreements"] = combined.disagreements
    if flags:
        counts["size_flags"] = [f["code"] for f in flags]

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
    # Timesheets found: an earlier "not a timesheet" (from the classifier or an earlier
    # extraction, before a reprocess) no longer applies.
    document.error = None
    timesheets_extracted.add(
        len(result.timesheets), {"parts": "many" if len(pieces) > 1 else "one"}
    )
    record_step(
        session,
        submission_id=submission.id,
        document_id=document.id,
        step=StepName.EXTRACT,
        result=StepResult.WARNING
        if missing_flag or flags or combined.disagreements
        else StepResult.SUCCESS,
        message=f"Found {len(result.timesheets)} timesheet(s) in {document.filename}"
        + (f" in {len(pieces)} parts" if len(pieces) > 1 else "")
        + (
            f"; {combined.joined} found in two parts and combined"
            if len(pieces) > 1 and combined.joined
            else ""
        )
        + (
            f"; {len(combined.disagreements)} day(s) read differently in the overlap"
            if combined.disagreements
            else ""
        )
        + ("; the document was too long to read in full" if split.capped else "")
        + (
            f"; {counts['people_missing']} of {people.total} people on the sheet "
            "missing"
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
        combined=combined,
        text=text,
        parts=len(pieces),
        missing_flag=missing_flag,
        size_flags=flags,
    )
