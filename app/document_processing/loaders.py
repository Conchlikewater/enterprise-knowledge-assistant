"""TXT and text-based PDF loaders with stable parse failures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pypdf import PdfReader

from app.core.exceptions import DocumentParseError, UnsupportedFileTypeError

TXT_MEDIA_TYPE: Final = "text/plain"
PDF_MEDIA_TYPE: Final = "application/pdf"


@dataclass(frozen=True, slots=True)
class DocumentSection:
    text: str
    page_number: int | None = None


def load_document(file_path: Path, media_type: str) -> list[DocumentSection]:
    if media_type == TXT_MEDIA_TYPE:
        return load_txt(file_path)
    if media_type == PDF_MEDIA_TYPE:
        return load_pdf(file_path)
    raise UnsupportedFileTypeError()


def load_txt(file_path: Path) -> list[DocumentSection]:
    try:
        text = file_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise DocumentParseError() from exc

    clean_text = _clean_text(text)
    if not clean_text:
        raise DocumentParseError()
    return [DocumentSection(text=clean_text)]


def load_pdf(file_path: Path) -> list[DocumentSection]:
    try:
        reader = PdfReader(file_path)
        if reader.is_encrypted:
            raise DocumentParseError()

        sections = []
        for page_number, page in enumerate(reader.pages, start=1):
            page_text = _clean_text(page.extract_text() or "")
            if page_text:
                sections.append(
                    DocumentSection(text=page_text, page_number=page_number)
                )
    except DocumentParseError:
        raise
    except Exception as exc:
        # pypdf can raise several parser-specific exception types. None of their
        # raw messages should cross the application boundary.
        raise DocumentParseError() from exc

    if not sections:
        raise DocumentParseError()
    return sections


def _clean_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()
