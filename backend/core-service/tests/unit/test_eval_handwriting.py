"""The handwriting evaluation script, run end to end against a mocked vision model and a
mocked extractor: no network, no GPU."""

import io
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from src.config.settings import settings
from src.handlers.http_clients import vision_reader
from src.handlers.http_clients.vision_reader import VisionResult
from src.schemas.extraction import ExtractedDay, ExtractedTimesheet, ExtractionResult
from src.tools import eval_handwriting as ev

TRANSCRIPT = """Name: Grace Hoper
| Day | Date | Hours |
|---|---|---|
| Mon | 12/10 | 8 |
| Tue | 13/10 | [UNCLEAR] |
| Wed | 14/10 | 7 |"""

EXPECTED = """file,employee_name,work_date,hours
grace.png,Grace Hopper,2026-10-12,8
grace.png,Grace Hopper,2026-10-13,7.5
grace.png,Grace Hopper,2026-10-14,7.5
broken.png,Ravi Kumar,2026-10-12,8
"""


@dataclass
class Reply:
    content: str


class FakeModel:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, messages: list[dict[str, Any]]) -> Reply:
        self.calls += 1
        return Reply(
            json.dumps(
                {
                    "classification": "mixed",
                    "confidence": 0.9,
                    "has_handwriting": True,
                    "has_handwritten_hours": True,
                    "has_printed_text": True,
                    "reason": "Printed table, hours in pen",
                    "transcription": TRANSCRIPT,
                }
            )
        )


def photo() -> bytes:
    out = io.BytesIO()
    Image.effect_noise((900, 1200), 60).convert("RGB").save(out, format="PNG")
    return out.getvalue()


async def fake_extract(markdown: str, filename: str) -> ExtractionResult:
    assert "Grace Hoper" in markdown  # the vision transcript is what gets extracted
    return ExtractionResult(
        timesheets=[
            ExtractedTimesheet(
                employee_name="Grace Hoper",
                days=[
                    ExtractedDay(work_date=date(2026, 10, 12), hours=8),
                    ExtractedDay(work_date=date(2026, 10, 14), hours=7),
                ],
                unreadable_days=["2026-10-13"],
                confidence=0.7,
            )
        ]
    )


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data = tmp_path / "eval_data"
    data.mkdir()
    (data / "grace.png").write_bytes(photo())
    (data / "broken.png").write_bytes(b"\x89PNG not really" * 2000)
    (data / "expected.csv").write_text(EXPECTED, encoding="utf-8")
    model = FakeModel()
    monkeypatch.setattr(vision_reader, "_default_model", lambda: model)
    for name in ("vision_enabled", "vision_model", "vision_base_url"):
        monkeypatch.setattr(
            settings, name, getattr(settings, name)
        )  # restored afterwards
    return data


def test_cer() -> None:
    assert ev.cer("Grace Hopper", "grace  hopper") == 0
    assert ev.cer("Grace Hopper", "Grace Hoper") == pytest.approx(1 / 12)
    assert ev.cer("Grace Hopper", None) == 1


def test_the_script_runs_against_a_mocked_model_and_writes_a_report(
    folder: Path, tmp_path: Path
) -> None:
    out = tmp_path / "eval-report.md"
    code = ev.main(
        [
            str(folder),
            "--model",
            "gemma-4-31b-it",
            "--base-url",
            "http://gpu:11434/v1",
            "--out",
            str(out),
        ],
        extract=fake_extract,
    )
    assert code == 0
    assert settings.vision_model == "gemma-4-31b-it"  # the override was applied

    report = out.read_text(encoding="utf-8")
    assert report.startswith("# Handwriting evaluation: gemma-4-31b-it")
    assert "gpu:11434" in report
    assert "| Date exact match | 66.7 % |" in report  # 2 of the 3 days found
    assert "| Hours exact match (per day) | 33.3 % |" in report  # only Monday right
    assert (
        "| Days marked [UNCLEAR] | 33.3 % |" in report
    )  # Tuesday: unreadable, not guessed
    assert "| Failures | 1 |" in report  # broken.png
    assert "2026-10-14: expected 7.5 h, got 7 h" in report
    assert "2026-10-13: marked unreadable [UNCLEAR]" in report
    assert "broken.png" in report
    assert "| grace.png | mixed | 1 |" in report  # the class the vision model saw


def test_scores(folder: Path) -> None:
    expected = ev.load_expected(folder / "expected.csv")

    def read(filename: str, extension: str, data: bytes) -> VisionResult:
        return vision_reader.read_with_vision(filename, extension, data)

    import asyncio

    results = asyncio.run(ev.evaluate(folder, expected, read, fake_extract))
    by_file = {r.file: r for r in results}
    grace = by_file["grace.png"]
    assert (grace.pages, grace.unclear_marks, grace.days) == (1, 1, 3)
    assert (grace.dates_ok, grace.hours_ok, grace.marked_unreadable) == (2, 1, 1)
    assert by_file["broken.png"].error is not None

    summary = ev.summarize(results)
    assert summary.failed == 1
    assert summary.name_cer == pytest.approx(1 / 12)
    assert summary.seconds_per_page is not None


def test_bad_expected_csv_is_reported(tmp_path: Path) -> None:
    bad = tmp_path / "expected.csv"
    bad.write_text("file,employee_name,work_date,hours\na.png,X,12/10/2026,8\n")
    with pytest.raises(ValueError, match="line 2"):
        ev.load_expected(bad)
    assert ev.main([str(tmp_path / "missing")]) == 2
