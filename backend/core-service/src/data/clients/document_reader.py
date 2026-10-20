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
"""

import logging
from functools import lru_cache
from io import BytesIO

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

from src.data.clients.document_limits import ReadLimit, prepare
from src.data.clients.plain_readers import (
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
