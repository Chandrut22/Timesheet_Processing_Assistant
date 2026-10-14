"""Extract Markdown text and tables from uploaded documents using Docling.

Supported formats:
    - PDF, including scanned PDFs
    - Images: PNG, JPG, JPEG, TIFF, BMP, WEBP
    - DOCX
    - XLSX

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
    """Convert uploaded document bytes into Markdown.

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

    try:
        document_stream = DocumentStream(
            name=filename,
            stream=BytesIO(data),
        )

        result = _converter().convert(
            document_stream,
            raises_on_error=True,
        )

        markdown = result.document.export_to_markdown().strip()

        if not markdown:
            raise DocumentReadError(f"No readable text found in '{filename}'.")

        logger.info(
            "Document extracted successfully: %s (%d characters)",
            filename,
            len(markdown),
        )

        return markdown

    except DocumentReadError:
        raise

    except Exception as exc:
        logger.exception(
            "Document extraction failed for '%s'",
            filename,
        )
        raise DocumentReadError(f"Could not read '{filename}': {exc}") from exc
