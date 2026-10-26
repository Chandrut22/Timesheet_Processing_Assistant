"""Extract Markdown text and tables from uploaded documents using Docling.

Supported formats:
    - PDF, including scanned PDFs
    - Images: PNG, JPG, JPEG, TIFF, BMP, WEBP
    - DOCX
    - XLSX
    - CSV and TXT (read directly, without Docling: plain_readers.py)

A PDF whose table Docling takes for a picture ("<!-- image -->") gets its own text
layer added, so the hours still reach the AI (plain_readers.with_pdf_text_layer).

OCR uses RapidOCR with the ONNX Runtime backend.

With VISION_ENABLED=true, photos and scans (PDFs with no text layer) are read by a
vision-language model instead (handlers/http_clients/vision_reader.py): RapidOCR
reads handwriting poorly.
read_document_full() says which way a file was read (read_method).
"""

import logging
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from typing import Literal

from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    RapidOcrOptions,
)
from docling.document_converter import (
    DocumentConverter,
    ImageFormatOption,
    PdfFormatOption,
)

from src.config.settings import settings
from src.core.services.documents.document_limits import ReadLimit, prepare
from src.core.services.documents.file_problems import file_problem
from src.core.services.documents.plain_readers import (
    PlainReadError,
    csv_to_markdown,
    pdf_text_layer,
    txt_to_text,
    with_pdf_text_layer,
)

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
    ".docx",
    ".xlsx",
    ".csv",
    ".txt",
}


class DocumentReadError(Exception):
    """Raised when a document cannot be converted or has no readable text."""


class UnreadableFileError(DocumentReadError):
    """The file is damaged or password-protected. The message is for people (it names
    the file and says what to ask the sender)."""


ReadMethod = Literal["docling", "plain", "vision"]


@dataclass(slots=True)
class ReadOutcome:
    """The text of a document and how it was read."""

    text: str
    limit: ReadLimit
    method: ReadMethod
    model: str | None = None  # the vision model, when method == "vision"
    pages_read: int | None = None
    unclear_marks: int = 0  # [UNCLEAR] in a vision transcription
    # What kind of writing the vision model saw (None when it was not used).
    writing_class: str | None = None
    writing_confidence: float | None = None
    has_handwriting: bool = False
    has_handwritten_hours: bool = False
    writing_reason: str | None = None


@lru_cache(maxsize=1)
def _converter() -> DocumentConverter:
    """Create and reuse one converter per process."""

    pipeline_options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
    )

    # Use the same OCR backend as the working Windows environment.
    pipeline_options.ocr_options = RapidOcrOptions(lang=["en"], backend="onnxruntime")

    return DocumentConverter(
        allowed_formats=[
            InputFormat.PDF,
            InputFormat.IMAGE,
            InputFormat.DOCX,
            InputFormat.XLSX,
        ],
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
            ),
            InputFormat.IMAGE: ImageFormatOption(
                pipeline_options=pipeline_options,
            ),
        },
    )


def read_document(filename: str, data: bytes) -> str:
    """Convert uploaded document bytes into Markdown (see read_document_with_limits)."""
    return read_document_with_limits(filename, data)[0]


def read_document_with_limits(filename: str, data: bytes) -> tuple[str, ReadLimit]:
    """The text and what was left out (read_document_full without the details)."""
    outcome = read_document_full(filename, data)
    return outcome.text, outcome.limit


def _extension(filename: str) -> str:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return f".{extension}" if extension else ""


def read_document_full(filename: str, data: bytes) -> ReadOutcome:
    """Read a document: the vision model for photos and scans (when VISION_ENABLED),
    otherwise Docling, or the plain readers for CSV / TXT. Raises DocumentReadError,
    DocumentTooLargeError, or VisionUnavailableError (temporary: retried later; a photo
    is never read with OCR instead, that would guess handwriting)."""
    if filename and filename.strip() and data:
        problem = file_problem(filename, _extension(filename), data)
        if problem is not None:  # before any reader: no reader crashes, no retries
            raise UnreadableFileError(problem)
    if filename and filename.strip() and data and settings.vision_enabled:
        from src.handlers.http_clients.vision_reader import (
            VisionReadError,
            needs_vision,
            read_with_vision,
        )

        extension = _extension(filename)
        if extension in SUPPORTED_EXTENSIONS and needs_vision(extension, data):
            try:
                result = read_with_vision(filename, extension, data)
            except VisionReadError as exc:
                raise DocumentReadError(str(exc)) from exc
            return ReadOutcome(
                result.markdown,
                result.limit,
                "vision",
                model=result.model,
                pages_read=result.pages_read,
                unclear_marks=result.unclear_marks,
                writing_class=result.writing_class,
                writing_confidence=result.writing_confidence,
                has_handwriting=result.has_handwriting,
                has_handwritten_hours=result.has_handwritten_hours,
                writing_reason=result.reason or None,
            )
    extension = _extension(filename) if filename else ""
    text, limit = _read_with_docling(filename, data)
    return ReadOutcome(text, limit, "plain" if extension in (".csv", ".txt") else "docling")


def _read_with_docling(filename: str, data: bytes) -> tuple[str, ReadLimit]:
    """Convert uploaded document bytes into Markdown, within the size limits.

    Big files are checked first (document_limits.prepare): only the first MAX_PAGES of a
    PDF and the first MAX_SHEETS sheets with data of a workbook are converted; hidden and
    empty sheets never are. Returns the text and what was left out. In refuse mode a file
    over the limit raises DocumentTooLargeError (its message says to split the file).

    Args:
        filename: Original filename, including its extension.
        data: Raw file bytes.

    Returns:
        Extracted text and tables in Markdown format.

    Raises:
        DocumentReadError: If the file type is unsupported, conversion
            fails, or no readable text is extracted.
    """

    if not filename or not filename.strip():
        raise DocumentReadError("A filename is required.")

    if not data:
        raise DocumentReadError(f"The uploaded file '{filename}' is empty.")

    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    extension = f".{extension}" if extension else ""

    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise DocumentReadError(
            f"Unsupported file type '{extension}'. Supported extensions: {supported}"
        )

    if extension in (".csv", ".txt"):
        try:
            text = (
                csv_to_markdown(data, filename)
                if extension == ".csv"
                else txt_to_text(data, filename)
            )
        except PlainReadError as exc:
            raise DocumentReadError(str(exc)) from exc
        return text, ReadLimit()

    prepared = prepare(filename, data)  # may raise DocumentTooLargeError (refuse mode)

    try:
        document_stream = DocumentStream(
            name=filename,
            stream=BytesIO(prepared.data),
        )

        if prepared.page_range is not None:
            result = _converter().convert(
                document_stream, raises_on_error=True, page_range=prepared.page_range
            )
        else:
            result = _converter().convert(document_stream, raises_on_error=True)

        markdown = result.document.export_to_markdown().strip()

        if extension == ".pdf":
            # Docling can take a table for a picture and drop its text: add the PDF's own
            # text layer when it holds numbers (hours, dates) that are missing.
            layer = pdf_text_layer(prepared.data, prepared.page_range)
            before = len(markdown)
            markdown = with_pdf_text_layer(markdown, layer) if markdown else layer
            if len(markdown) != before:
                logger.info("Added the PDF text layer for %s (%d characters)", filename, len(layer))

        if not markdown:
            raise DocumentReadError(f"No readable text found in '{filename}'.")

        logger.info(
            "Document extracted successfully: %s (%d characters)",
            filename,
            len(markdown),
        )

        return markdown, prepared.limit

    except DocumentReadError:
        raise

    except Exception as exc:
        logger.exception(
            "Document extraction failed for '%s'",
            filename,
        )
        raise DocumentReadError(f"Could not read '{filename}': {exc}") from exc
