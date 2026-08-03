"""Small metadata-preserving chunker without framework-specific objects."""

from __future__ import annotations

from hashlib import sha256
from uuid import UUID, uuid4

from app.document_processing.loaders import DocumentSection
from app.domain.models import Chunk

_BOUNDARIES = ("\n\n", "\n", ". ", "。", "! ", "? ", "；", "; ", "，", ", ", " ")


def chunk_sections(
    sections: list[DocumentSection],
    document_id: UUID,
    filename: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= chunk_overlap < chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")
    if not filename:
        raise ValueError("filename must not be empty")

    chunks: list[Chunk] = []
    for section in sections:
        text = section.text.strip()
        if not text:
            continue
        for chunk_text in _split_text(text, chunk_size, chunk_overlap):
            chunks.append(
                Chunk(
                    chunk_id=uuid4(),
                    document_id=document_id,
                    chunk_index=len(chunks),
                    text=chunk_text,
                    filename=filename,
                    page_number=section.page_number,
                    content_hash=sha256(chunk_text.encode("utf-8")).hexdigest(),
                )
            )
    return chunks


def _split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    pieces: list[str] = []
    start = 0
    text_length = len(text)

    while start < text_length:
        target_end = min(start + chunk_size, text_length)
        end = target_end
        if target_end < text_length:
            minimum_end = start + max(1, chunk_size // 2)
            for boundary in _BOUNDARIES:
                boundary_index = text.rfind(boundary, minimum_end, target_end)
                if boundary_index >= 0:
                    end = boundary_index + len(boundary)
                    break

        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= text_length:
            break

        next_start = max(end - chunk_overlap, start + 1)
        while next_start < end and text[next_start].isspace():
            next_start += 1
        start = next_start

    return pieces
