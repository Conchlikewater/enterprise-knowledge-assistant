"""Public document API models that never expose local storage paths."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.models import Document, DocumentStatus


class DocumentResponse(BaseModel):
    document_id: UUID
    filename: str
    media_type: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    status: DocumentStatus
    chunk_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, document: Document) -> "DocumentResponse":
        return cls(
            document_id=document.document_id,
            filename=document.filename,
            media_type=document.media_type,
            size_bytes=document.size_bytes,
            sha256=document.sha256,
            status=document.status,
            chunk_count=document.chunk_count,
            created_at=document.created_at,
            updated_at=document.updated_at,
        )


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    count: int = Field(ge=0)
