"""Readers that don't need Docling, and a safety net for when Docling drops text.

  - CSV and TXT files are read directly: a CSV becomes a Markdown table (the same shape
    Docling gives Excel), a TXT file is its text.
  - PDF text layer: Docling sometimes takes a table for a picture and writes only
    "<!-- image -->" for it, so the hours never reach the AI (seen on generated PDFs:
    name and week read, no days). When that happens and the PDF has a text layer with
    numbers Docling's output lacks, that text is added below Docling's output.

Pure functions apart from pypdfium2 (already installed with Docling)."""

import csv
import io
import re

IMAGE_PLACEHOLDER = "<!-- image -->"
MAX_TEXT_LAYER_CHARS = 60_000  # the AI sees at most LLM_MAX_INPUT_CHARS anyway
_NUMBER = re.compile(r"\d+(?:[.:]\d+)?")


class PlainReadError(Exception):
    """The file could not be decoded or holds no text."""


def decode_text(data: bytes) -> str:
    """UTF-8 (with or without BOM), else Windows-1252 (Excel's "CSV" on Windows)."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")  # never fails: every byte is a character


def _cell(value: str) -> str:
    return " ".join(value.split()).replace("|", "\\|")


def csv_to_markdown(data: bytes, filename: str = "file.csv") -> str:
    """A CSV (comma, semicolon, tab or pipe separated) as one Markdown table."""
    text = decode_text(data).strip()
    if not text:
        raise PlainReadError(f"'{filename}' is empty.")
    sample = text[:4096]
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]
    if not rows:
        raise PlainReadError(f"No rows found in '{filename}'.")
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(_cell(c) for c in rows[0]) + " |"]
    lines.append("|" + "---|" * width)
    lines += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def txt_to_text(data: bytes, filename: str = "file.txt") -> str:
    text = decode_text(data).strip()
    if not text:
        raise PlainReadError(f"'{filename}' is empty.")
    return text


def pdf_text_layer(data: bytes, page_range: tuple[int, int] | None = None) -> str:
    """The PDF's own text (no OCR), page by page; '' for a scan or a broken file."""
    try:
        import pypdfium2

        document = pypdfium2.PdfDocument(data)
    except Exception:
        return ""
    try:
        first, last = page_range or (1, len(document))
        pages: list[str] = []
        for number in range(first, min(last, len(document)) + 1):
            page = document[number - 1]
            textpage = page.get_textpage()
            text = textpage.get_text_range().replace("\r\n", "\n").strip()
            textpage.close()
            page.close()
            if text:
                pages.append(f"--- page {number} ---\n{text}")
        return "\n\n".join(pages)[:MAX_TEXT_LAYER_CHARS]
    except Exception:
        return ""
    finally:
        document.close()


def missing_numbers(markdown: str, text_layer: str) -> list[str]:
    """Numbers (hours, dates, totals) in the text layer that Docling's output lacks."""
    have = set(_NUMBER.findall(markdown))
    return [n for n in dict.fromkeys(_NUMBER.findall(text_layer)) if n not in have]


def with_pdf_text_layer(markdown: str, text_layer: str, min_missing: int = 3) -> str:
    """Docling's output, plus the PDF's text layer when Docling replaced part of the page
    by a picture and the text layer holds at least `min_missing` numbers it dropped."""
    if IMAGE_PLACEHOLDER not in markdown or not text_layer.strip():
        return markdown
    if len(missing_numbers(markdown, text_layer)) < min_missing:
        return markdown
    return (
        f"{markdown}\n\n## Text layer of the PDF\n\n"
        "(The reader saw part of the page as a picture; this is the PDF's own text, "
        "including what that picture covered.)\n\n"
        f"{text_layer}"
    )
