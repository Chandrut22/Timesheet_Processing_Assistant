"""Evaluate the attachment classifier on your own labelled sample files, BEFORE switching
skipping on.

Put the files in two folders (any names inside):

    samples/
      timesheet/       real timesheets: clean PDFs, Excel, scans, phone photos, handwritten
      not_timesheet/   invoices, payslips, letters, logos, random attachments

Run (from core-service/, with JEV_API_KEY in .env; Docling reads the files, like the worker):

    uv run python -m src.tools.evaluate_classifier ..\\samples --out classifier-eval.csv

It writes one CSV row per file and prints, for thresholds 0.1 / 0.2 / 0.3:
  - real timesheets that WOULD BE WRONGLY SKIPPED   <- must be 0 to switch skipping on
  - non-timesheets skipped (= AI extraction calls saved)
  - average classifier time, and the estimated cost
Nothing is written to the database. Only the start of each document's text is sent to Jev."""

import argparse
import asyncio
import csv
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from src.core.services.attachment_classifier import (
    ClassifierResult,
    should_skip,
)

FOLDERS = {"timesheet": True, "not_timesheet": False}
THRESHOLDS = (0.1, 0.2, 0.3)
COST_PER_CALL_USD = 0.0007  # as reported in TypeSafe's announcement; check your plan


@dataclass(slots=True)
class Row:
    file: str
    is_timesheet: bool
    label: str | None
    p_timesheet: float | None
    duration_ms: int
    error: str | None


@dataclass(slots=True)
class ThresholdReport:
    threshold: float
    wrongly_skipped: list[str]  # real timesheets the classifier would have skipped
    saved: int  # non-timesheets skipped
    not_timesheets: int


Reader = Callable[[Path], str]
Classifier = Callable[[str], Awaitable[ClassifierResult]]


def files_in(samples: Path) -> list[tuple[Path, bool]]:
    found: list[tuple[Path, bool]] = []
    for folder, is_timesheet in FOLDERS.items():
        base = samples / folder
        if base.is_dir():
            found += [(p, is_timesheet) for p in sorted(base.rglob("*")) if p.is_file()]
    return found


async def evaluate(samples: Path, read: Reader, classify: Classifier) -> list[Row]:
    rows: list[Row] = []
    for path, is_timesheet in files_in(samples):
        name = path.relative_to(samples).as_posix()
        try:
            text = await asyncio.to_thread(read, path)
            result = await classify(text)
            rows.append(
                Row(name, is_timesheet, result.label, result.p_timesheet, result.duration_ms, None)
            )
        except Exception as exc:  # a broken file or a failed call must not stop the run
            rows.append(Row(name, is_timesheet, None, None, 0, f"{type(exc).__name__}: {exc}"))
        print(f"  {name:<50} {rows[-1].label or 'ERROR':<10} {rows[-1].p_timesheet}")
    return rows


def report(rows: list[Row], threshold: float) -> ThresholdReport:
    wrongly: list[str] = []
    saved = 0
    for row in rows:
        if row.label is None:
            continue  # an error never skips
        result = ClassifierResult(row.label, row.p_timesheet, "", row.duration_ms)
        if should_skip(result, threshold):
            if row.is_timesheet:
                wrongly.append(row.file)
            else:
                saved += 1
    not_timesheets = sum(1 for r in rows if not r.is_timesheet)
    return ThresholdReport(threshold, wrongly, saved, not_timesheets)


def write_csv(rows: list[Row], out: Path) -> None:
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["file", "truth", "label", "p_timesheet", "ms", "error"])
        for r in rows:
            truth = "timesheet" if r.is_timesheet else "not_timesheet"
            writer.writerow([r.file, truth, r.label, r.p_timesheet, r.duration_ms, r.error])


def summary(rows: list[Row]) -> str:
    timed = [r.duration_ms for r in rows if r.label is not None]
    unknown = sum(1 for r in rows if r.label is not None and r.p_timesheet is None)
    lines = [
        f"\nFiles: {len(rows)} ({sum(r.is_timesheet for r in rows)} timesheets, "
        f"{sum(not r.is_timesheet for r in rows)} other), errors: "
        f"{sum(r.label is None for r in rows)}, no P(timesheet) in the answer: {unknown}",
        f"Average classifier time: {sum(timed) / len(timed):.0f} ms" if timed else "",
        f"Estimated cost: ${len(timed) * COST_PER_CALL_USD:.4f} for {len(timed)} calls",
        "",
        "threshold | wrongly skipped timesheets | non-timesheets skipped (AI calls saved)",
    ]
    for t in THRESHOLDS:
        rep = report(rows, t)
        share = f"{rep.saved}/{rep.not_timesheets}" if rep.not_timesheets else "0/0"
        lines.append(f"   {t:.1f}    | {len(rep.wrongly_skipped):^26} | {share}")
        lines += [f"             ! would skip: {name}" for name in rep.wrongly_skipped]
    safe = [t for t in THRESHOLDS if not report(rows, t).wrongly_skipped]
    lines.append(
        f"\nSafe thresholds (no timesheet skipped): {', '.join(str(t) for t in safe) or 'none'}"
        + ("" if safe else ": keep CLASSIFIER_ENABLED=false or stay in shadow mode")
    )
    if unknown:
        lines.append(
            "Some answers had no usable P(timesheet): check the response format in "
            "TypeSafe's docs (those files are never skipped)."
        )
    return "\n".join(line for line in lines if line is not None)


def _read_with_docling(path: Path) -> str:
    if path.suffix.lower() in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    from src.core.services.documents.document_reader import read_document

    return read_document(path.name, path.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the attachment classifier")
    parser.add_argument("samples", type=Path, help="folder with timesheet/ and not_timesheet/")
    parser.add_argument("--out", type=Path, default=Path("classifier-eval.csv"))
    args = parser.parse_args()
    if not files_in(args.samples):
        print(f"No files in {args.samples}/timesheet or {args.samples}/not_timesheet")
        return 2

    from src.handlers.http_clients.jev_client import classify

    rows = asyncio.run(evaluate(args.samples, _read_with_docling, classify))
    write_csv(rows, args.out)
    print(summary(rows))
    print(f"\nPer-file results: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
