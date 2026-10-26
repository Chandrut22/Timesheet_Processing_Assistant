"""CSV / TXT read without Docling, and the PDF text-layer safety net (found in the
first batch run: CSVs were refused as unsupported; PDF tables came out as a picture)."""

from pathlib import Path

import pytest

from src.constants.file_types import skip_reason
from src.core.services.document_tables import count_people
from src.core.services.documents.plain_readers import (
    IMAGE_PLACEHOLDER,
    PlainReadError,
    csv_to_markdown,
    decode_text,
    missing_numbers,
    pdf_text_layer,
    txt_to_text,
    with_pdf_text_layer,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "table_as_picture.pdf"

CSV = (
    "Employee ID,Employee Name,Date,Hours\r\n"
    + "".join(f"SYN-EMP-016,Hannah Weiss,2026-10-0{d},7.5\r\n" for d in range(5, 10))
).encode()


def test_csv_and_txt_are_supported_now() -> None:
    assert skip_reason(".csv", 243) is None
    assert skip_reason(".txt", 100) is None
    assert skip_reason(".zip", 100) is not None


def test_csv_becomes_a_markdown_table() -> None:
    text = csv_to_markdown(CSV)
    lines = text.splitlines()
    assert lines[0] == "| Employee ID | Employee Name | Date | Hours |"
    assert lines[1] == "|---|---|---|---|"
    assert lines[2] == "| SYN-EMP-016 | Hannah Weiss | 2026-10-05 | 7.5 |"
    assert len(lines) == 7


def test_the_csv_table_is_read_as_one_person() -> None:
    count = count_people(csv_to_markdown(CSV))
    assert count is not None and count.total == 1


@pytest.mark.parametrize(
    "raw",
    [
        b"Name;Mon;Tue\nGrace Okoye;8;8\n",  # European Excel: semicolons
        b"Name\tMon\tTue\nGrace Okoye\t8\t8\n",  # tab separated
        "﻿Name,Mon,Tue\nGrace Okoye,8,8\n".encode(),  # UTF-8 with BOM
    ],
)
def test_other_separators_and_a_bom(raw: bytes) -> None:
    assert csv_to_markdown(raw).splitlines()[2] == "| Grace Okoye | 8 | 8 |"


def test_windows_encoded_names_and_pipes() -> None:
    raw = "Name,Note\nJosé Müller,a|b\n".encode("cp1252")
    assert csv_to_markdown(raw).splitlines()[2] == "| José Müller | a\\|b |"


def test_ragged_rows_are_padded() -> None:
    assert csv_to_markdown(b"A,B,C\n1,2\n").splitlines()[2] == "| 1 | 2 |  |"


def test_empty_files_are_refused() -> None:
    with pytest.raises(PlainReadError):
        csv_to_markdown(b"  \n ")
    with pytest.raises(PlainReadError):
        txt_to_text(b"")


def test_txt_is_its_text() -> None:
    assert txt_to_text(b"Grace worked 8 h Monday\n") == "Grace worked 8 h Monday"
    assert decode_text(b"\xe9") == "é"  # not UTF-8: Windows-1252


# --- the PDF text layer -----------------------------------------------------------------

DOCLING_SAW_A_PICTURE = (
    "## ABC Staffing Solutions Pvt Ltd\n\nWeekly Timesheet Employee: Priya Nair "
    "ID: SYN-EMP-002 Week starting: 2026-10-05\n\n<!-- image -->\n\n"
    "Employee signature: ____________ Supervisor: approved"
)


def test_the_text_layer_of_the_batch_pdf_has_every_day() -> None:
    layer = pdf_text_layer(FIXTURE.read_bytes())
    assert "--- page 1 ---" in layer
    assert "2026-10-09 Friday 8" in layer and "Total 40" in layer


def test_page_range_and_broken_files() -> None:
    assert pdf_text_layer(FIXTURE.read_bytes(), (2, 5)) == ""  # the PDF has one page
    assert pdf_text_layer(b"%PDF-1.7 broken") == ""


def test_text_layer_is_added_when_docling_dropped_the_table() -> None:
    layer = pdf_text_layer(FIXTURE.read_bytes())
    assert len(missing_numbers(DOCLING_SAW_A_PICTURE, layer)) >= 3
    out = with_pdf_text_layer(DOCLING_SAW_A_PICTURE, layer)
    assert out.startswith(DOCLING_SAW_A_PICTURE)
    assert "## Text layer of the PDF" in out and "2026-10-07 Wednesday 8" in out


def test_nothing_is_added_when_docling_read_the_table() -> None:
    read_well = "| Date | Hours |\n|---|---|\n| 2026-10-05 | 8 |\n" + IMAGE_PLACEHOLDER
    assert with_pdf_text_layer(read_well, "Date Hours\n2026-10-05 8") == read_well
    no_picture = "Some text 1 2 3"
    assert with_pdf_text_layer(no_picture, "4 5 6 7 8") == no_picture


def test_a_scan_has_no_text_layer_so_nothing_changes() -> None:
    assert with_pdf_text_layer(DOCLING_SAW_A_PICTURE, "") == DOCLING_SAW_A_PICTURE
