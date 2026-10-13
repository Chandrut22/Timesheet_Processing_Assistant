"""Turn an uploaded file into Markdown text with Docling.

PDF, DOCX, XLSX and images; scanned pages and photos go through OCR."""

import logging
from functools import lru_cache
from io import BytesIO

from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, ImageFormatOption, PdfFormatOption

logger = logging.getLogger(__name__)


class DocumentReadError(Exception):
    """Corrupt, password-protected, or no readable text."""


@lru_cache(maxsize=1)
def _converter() -> DocumentConverter:
    """Built once per process: loading the layout and OCR models takes seconds and ~1 GB RAM."""
    options = PdfPipelineOptions(do_ocr=True, do_table_structure=True)
    return DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.IMAGE, InputFormat.DOCX, InputFormat.XLSX],
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=options),
            InputFormat.IMAGE: ImageFormatOption(pipeline_options=options),
        },
    )


def read_document(filename: str, data: bytes) -> str:
    """CPU-heavy and blocking: call it with asyncio.to_thread()."""
    try:
        result = _converter().convert(
            DocumentStream(name=filename, stream=BytesIO(data)), raises_on_error=True
        )
    except Exception as exc:
        raise DocumentReadError(f"Could not read '{filename}': {exc}") from exc

    text = result.document.export_to_markdown().strip()
    if not text:
        raise DocumentReadError(f"No readable text found in '{filename}'.")
    return text
