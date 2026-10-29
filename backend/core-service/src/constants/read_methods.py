"""How a document was turned into text (documents.read_method)."""

from enum import StrEnum

# Written by the vision model in place of anything it cannot read (counted in code).
UNCLEAR_MARK = "[UNCLEAR]"


class ReadMethod(StrEnum):
    DOCLING = "docling"  # Docling (+ RapidOCR for pictures): typed PDF, DOCX, XLSX, ...
    PLAIN = "plain"  # CSV / TXT read directly
    VISION = "vision"  # a vision-language model: handwriting, photos, scans


class WritingClass(StrEnum):
    """How a photo / scan is written, as the vision model saw it
    (documents.writing_class)."""

    PRINTED_ONLY = "printed_only"  # printed or typed (a signature alone stays here)
    HANDWRITTEN_ONLY = "handwritten_only"
    MIXED = "mixed"  # printed form filled in by hand, handwritten corrections, ...
    NO_TEXT = "no_text"
    UNCERTAIN = "uncertain"  # blurry, cut off, low confidence, or no usable answer
