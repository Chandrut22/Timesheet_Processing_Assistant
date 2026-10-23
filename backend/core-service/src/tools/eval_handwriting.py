"""Compare vision models on YOUR handwritten timesheets before choosing one.

Put the photos / scans in a folder with an expected.csv (one row per person per day):

    eval_data/handwritten/
      grace-week41.jpg
      ravi-scan.pdf
      expected.csv        file,employee_name,work_date,hours
                          grace-week41.jpg,Grace Hopper,2026-10-12,8
                          grace-week41.jpg,Grace Hopper,2026-10-13,7.5

Run (from core-service/; the extraction step uses your normal LLM_* settings):

    uv run python -m src.tools.eval_handwriting eval_data/handwritten \\
        --model gemma4:31b-cloud --base-url https://ollama.com/v1 --out eval-report.md

Each file is read by the vision model exactly like the worker does (vision_reader), then
extracted. The Markdown report gives, per model run:
  - name CER        character error rate of the employee name (0 = perfect)
  - date match      expected days that were found on the right date
  - hours match     expected days with exactly the right hours
  - [UNCLEAR] rate  expected days the model marked unreadable instead of guessing
  - seconds / page  and the files that failed, with the reason
Run again with another --model / --base-url (Qwen3-VL, GLM-OCR, ...) to compare. The
key, if your server needs one, comes from VISION_API_KEY in .env (never the command
line). Nothing is written to the database. eval_data/ and eval-report*.md are in
.gitignore: never commit real timesheets."""

import argparse
import asyncio
import csv
import sys
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

from src.config.settings import settings
from src.data.clients.vision_reader import VisionResult, read_with_vision
from src.schemas.extraction import ExtractionResult

SUPPORTED = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".pdf"}
EXPECTED_COLUMNS = ("file", "employee_name", "work_date", "hours")


@dataclass(frozen=True, slots=True)
class ExpectedDay:
    file: str
    employee_name: str
    work_date: date
    hours: Decimal


@dataclass(slots=True)
class FileResult:
    file: str
    pages: int = 0
    seconds: float = 0.0
    unclear_marks: int = 0
    writing_class: str = ""  # printed_only / mixed / handwritten_only / ...
    names: list[tuple[str, str, float]] = field(default_factory=list)  # expected, got, CER
    days: int = 0
    dates_ok: int = 0
    hours_ok: int = 0
    marked_unreadable: int = 0
    misses: list[str] = field(default_factory=list)
    error: str | None = None


Reader = Callable[[str, str, bytes], VisionResult]
Extractor = Callable[[str, str], Awaitable[ExtractionResult]]


# --- inputs ------------------------------------------------------------------------------


def load_expected(path: Path) -> dict[str, list[ExpectedDay]]:
    """expected.csv grouped by file. Raises ValueError naming the bad line."""
    by_file: dict[str, list[ExpectedDay]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = set(EXPECTED_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path.name} needs the columns {', '.join(EXPECTED_COLUMNS)}")
        for line, row in enumerate(reader, start=2):
            try:
                day = ExpectedDay(
                    file=row["file"].strip(),
                    employee_name=row["employee_name"].strip(),
                    work_date=date.fromisoformat(row["work_date"].strip()),
                    hours=Decimal(row["hours"].strip()),
                )
            except (ValueError, InvalidOperation) as exc:
                raise ValueError(f"{path.name} line {line}: {exc}") from None
            by_file[day.file].append(day)
    return dict(by_file)


# --- scoring -----------------------------------------------------------------------------


def _norm(name: str | None) -> str:
    return " ".join((name or "").lower().split())


def levenshtein(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def _h(hours: Decimal) -> str:
    return format(hours.normalize(), "f")  # 7.50 -> 7.5, 8.0 -> 8


def cer(expected: str, got: str | None) -> float:
    """Character error rate of `got` against `expected` (case and spacing ignored)."""
    truth, guess = _norm(expected), _norm(got)
    if not truth:
        return 0.0 if not guess else 1.0
    return min(1.0, levenshtein(truth, guess) / len(truth))


def score(result: FileResult, expected: list[ExpectedDay], extracted: ExtractionResult) -> None:
    """Fill the name / date / hours / [UNCLEAR] counts for one file."""
    sheets = extracted.timesheets
    by_person: dict[str, list[ExpectedDay]] = defaultdict(list)
    for day in expected:
        by_person[day.employee_name].append(day)

    for person, days in by_person.items():
        best = min(sheets, key=lambda s: cer(person, s.employee_name), default=None)
        got_name = best.employee_name if best else None
        result.names.append((person, got_name or "", cer(person, got_name)))
        found = {d.work_date: d.hours for d in (best.days if best else []) if d.work_date}
        unreadable = set(best.unreadable_days) if best else set()
        for day in days:
            result.days += 1
            iso = day.work_date.isoformat()
            if day.work_date in found:
                result.dates_ok += 1
                got = Decimal(str(found[day.work_date]))
                if abs(got - day.hours) < Decimal("0.01"):
                    result.hours_ok += 1
                else:
                    result.misses.append(
                        f"{person} {iso}: expected {_h(day.hours)} h, got {_h(got)} h"
                    )
            elif iso in unreadable:
                result.marked_unreadable += 1
                result.misses.append(f"{person} {iso}: marked unreadable [UNCLEAR]")
            else:
                result.misses.append(f"{person} {iso}: not found")


# --- the run -----------------------------------------------------------------------------


def files_in(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED)


async def evaluate(
    folder: Path,
    expected: dict[str, list[ExpectedDay]],
    read: Reader,
    extract: Extractor,
) -> list[FileResult]:
    results: list[FileResult] = []
    for path in files_in(folder):
        if path.name not in expected:
            print(f"  {path.name:<40} skipped (not in expected.csv)")
            continue
        result = FileResult(path.name)
        try:
            started = time.monotonic()
            vision = await asyncio.to_thread(
                read, path.name, path.suffix.lower(), path.read_bytes()
            )
            result.seconds = time.monotonic() - started
            result.pages = vision.pages_read
            result.unclear_marks = vision.unclear_marks
            result.writing_class = vision.writing_class
            score(result, expected[path.name], await extract(vision.markdown, path.name))
        except Exception as exc:  # one bad file must not stop the comparison
            result.error = f"{type(exc).__name__}: {str(exc)[:200]}"
        results.append(result)
        status = result.error or f"{result.hours_ok}/{result.days} days right"
        print(f"  {path.name:<40} {status}")
    for name in sorted(set(expected) - {p.name for p in files_in(folder)}):
        results.append(FileResult(name, error="FileNotFoundError: listed in expected.csv"))
    return results


@dataclass(frozen=True, slots=True)
class Summary:
    files: int
    failed: int
    name_cer: float | None
    date_match: float | None
    hours_match: float | None
    unreadable_rate: float | None
    seconds_per_page: float | None


def summarize(results: list[FileResult]) -> Summary:
    ok = [r for r in results if r.error is None]
    names = [c for r in ok for _, _, c in r.names]
    days = sum(r.days for r in ok)
    pages = sum(r.pages for r in ok)

    def share(n: int) -> float | None:
        return n / days if days else None

    return Summary(
        files=len(results),
        failed=len(results) - len(ok),
        name_cer=sum(names) / len(names) if names else None,
        date_match=share(sum(r.dates_ok for r in ok)),
        hours_match=share(sum(r.hours_ok for r in ok)),
        unreadable_rate=share(sum(r.marked_unreadable for r in ok)),
        seconds_per_page=sum(r.seconds for r in ok) / pages if pages else None,
    )


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f} %"


def render_report(results: list[FileResult], *, model: str, base_url: str) -> str:
    s = summarize(results)
    host = urlparse(base_url).netloc or base_url
    lines = [
        f"# Handwriting evaluation: {model}",
        "",
        f"Server: {host} · {datetime.now(UTC):%Y-%m-%d %H:%M} UTC · "
        f"{s.files} files, {s.failed} failed",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Name CER (lower is better) | {'—' if s.name_cer is None else f'{s.name_cer:.3f}'} |",
        f"| Date exact match | {_pct(s.date_match)} |",
        f"| Hours exact match (per day) | {_pct(s.hours_match)} |",
        f"| Days marked [UNCLEAR] | {_pct(s.unreadable_rate)} |",
        "| Seconds per page | "
        + ("—" if s.seconds_per_page is None else f"{s.seconds_per_page:.1f}")
        + " |",
        f"| Failures | {s.failed} |",
        "",
        "## Per file",
        "",
        "| File | Class | Pages | s/page | [UNCLEAR] marks | Name (CER) | Dates | Hours | Error |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        names = "; ".join(f"{got or '—'} ({c:.2f})" for _, got, c in r.names) or "—"
        per_page = f"{r.seconds / r.pages:.1f}" if r.pages else "—"
        lines.append(
            f"| {_cell(r.file)} | {r.writing_class or '—'} | {r.pages} | {per_page} | "
            f"{r.unclear_marks} | "
            f"{_cell(names)} | {r.dates_ok}/{r.days} | {r.hours_ok}/{r.days} | "
            f"{_cell(r.error or '')} |"
        )
    misses = [(r.file, m) for r in results for m in r.misses]
    if misses:
        lines += ["", "## Days not right", ""]
        lines += [f"- {_cell(file)}: {_cell(miss)}" for file, miss in misses]
    return "\n".join(lines) + "\n"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


# --- command line ------------------------------------------------------------------------


def configure(model: str | None, base_url: str | None) -> None:
    """Point the vision reader at the model under test (this process only)."""
    from src.data.clients.llm import get_vision_model

    if model:
        settings.vision_model = model
    if base_url:
        settings.vision_base_url = base_url
    settings.vision_enabled = True
    get_vision_model.cache_clear()


def _read(filename: str, extension: str, data: bytes) -> VisionResult:
    return read_with_vision(filename, extension, data)


async def _extract(markdown: str, filename: str) -> ExtractionResult:
    from src.control.agents.extraction_agent import extract_timesheets

    return await extract_timesheets(
        document_text=markdown, filename=filename, received_at=datetime.now(UTC)
    )


def main(
    argv: list[str] | None = None, *, read: Reader = _read, extract: Extractor | None = None
) -> int:
    parser = argparse.ArgumentParser(description="Compare vision models on handwritten sheets")
    parser.add_argument("folder", type=Path, help="images / scans plus expected.csv")
    parser.add_argument("--expected", type=Path, help="default: <folder>/expected.csv")
    parser.add_argument("--model", help="model name exactly as the server lists it")
    parser.add_argument("--base-url", help="OpenAI-compatible endpoint, e.g. http://host:11434/v1")
    parser.add_argument("--out", type=Path, default=Path("eval-report.md"))
    args = parser.parse_args(argv)

    expected_path = args.expected or args.folder / "expected.csv"
    if not expected_path.is_file():
        print(f"No {expected_path}: see the module docstring for its format.")
        return 2
    try:
        expected = load_expected(expected_path)
    except ValueError as exc:
        print(exc)
        return 2
    configure(args.model, args.base_url)
    if not settings.vision_model or not settings.vision_base_url:
        print("Give --model and --base-url (or VISION_MODEL / VISION_BASE_URL in .env).")
        return 2

    print(f"Model {settings.vision_model} on {urlparse(settings.vision_base_url).netloc}")
    results = asyncio.run(evaluate(args.folder, expected, read, extract or _extract))
    report = render_report(results, model=settings.vision_model, base_url=settings.vision_base_url)
    args.out.write_text(report, encoding="utf-8")
    s = summarize(results)
    print(
        f"\nHours right: {_pct(s.hours_match)} · dates right: {_pct(s.date_match)} · "
        f"[UNCLEAR]: {_pct(s.unreadable_rate)} · failures: {s.failed}\nReport: {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
