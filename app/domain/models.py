"""Framework-independent V1 domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from pathlib import Path
from uuid import UUID


def utc_now() -> datetime:
    return datetime.now(UTC)


class DocumentStatus(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class IngestionJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Document:
    document_id: UUID
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    status: DocumentStatus
    stored_path: Path
    chunk_count: int = 0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.filename:
            raise ValueError("filename must not be empty")
        if self.size_bytes < 0 or self.chunk_count < 0:
            raise ValueError("sizes and counts must not be negative")
        if len(self.sha256) != 64:
            raise ValueError("sha256 must contain 64 hexadecimal characters")
        try:
            int(self.sha256, 16)
        except ValueError as exc:
            raise ValueError("sha256 must contain 64 hexadecimal characters") from exc


@dataclass(frozen=True, slots=True)
class IngestionJob:
    job_id: UUID
    document_id: UUID
    status: IngestionJobStatus
    attempt_count: int = 0
    error_code: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.attempt_count < 0:
            raise ValueError("attempt_count must not be negative")
        if self.error_code is not None and not self.error_code.strip():
            raise ValueError("error_code must not be blank")
        if self.status is IngestionJobStatus.PENDING:
            if self.started_at is not None or self.completed_at is not None:
                raise ValueError("pending jobs cannot have processing timestamps")
        if self.status is IngestionJobStatus.RUNNING:
            if self.started_at is None:
                raise ValueError("running jobs require a start timestamp")
            if self.completed_at is not None:
                raise ValueError("running jobs cannot have a completion timestamp")
        if self.status in {IngestionJobStatus.READY, IngestionJobStatus.FAILED}:
            if self.started_at is None:
                raise ValueError("terminal jobs require a start timestamp")
            if self.completed_at is None:
                raise ValueError("terminal jobs require a completion timestamp")
        if self.status is IngestionJobStatus.READY and self.error_code is not None:
            raise ValueError("ready jobs cannot contain an error code")
        if self.status is IngestionJobStatus.FAILED and self.error_code is None:
            raise ValueError("failed jobs require an error code")
        if self.status in {IngestionJobStatus.PENDING, IngestionJobStatus.RUNNING}:
            if self.error_code is not None:
                raise ValueError("active jobs cannot contain an error code")


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: UUID
    document_id: UUID
    chunk_index: int
    text: str
    filename: str
    content_hash: str
    page_number: int | None = None

    def __post_init__(self) -> None:
        if self.chunk_index < 0:
            raise ValueError("chunk_index must not be negative")
        if not self.text.strip():
            raise ValueError("chunk text must not be empty")
        if len(self.content_hash) != 64:
            raise ValueError("content_hash must contain 64 hexadecimal characters")
        try:
            int(self.content_hash, 16)
        except ValueError as exc:
            raise ValueError(
                "content_hash must contain 64 hexadecimal characters"
            ) from exc
        if self.page_number is not None and self.page_number < 1:
            raise ValueError("page_number must be positive when present")


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    chunk_id: UUID
    document_id: UUID
    filename: str
    text: str
    score: float
    page_number: int | None = None

    def __post_init__(self) -> None:
        if not self.filename:
            raise ValueError("filename must not be empty")
        if not self.text.strip():
            raise ValueError("retrieval text must not be empty")
        if not isfinite(self.score):
            raise ValueError("retrieval score must be finite")
        if self.page_number is not None and self.page_number < 1:
            raise ValueError("page_number must be positive when present")


@dataclass(frozen=True, slots=True)
class Citation:
    citation_number: int
    document_id: UUID
    chunk_id: UUID
    filename: str
    excerpt: str
    score: float
    page_number: int | None = None

    @classmethod
    def from_result(
        cls,
        result: RetrievalResult,
        citation_number: int,
        excerpt_limit: int = 240,
    ) -> Citation:
        if citation_number < 1:
            raise ValueError("citation_number must be positive")
        if excerpt_limit < 1:
            raise ValueError("excerpt_limit must be positive")
        compact_text = " ".join(result.text.split())
        excerpt = compact_text[:excerpt_limit]
        return cls(
            citation_number=citation_number,
            document_id=result.document_id,
            chunk_id=result.chunk_id,
            filename=result.filename,
            page_number=result.page_number,
            excerpt=excerpt,
            score=result.score,
        )


@dataclass(frozen=True, slots=True)
class AnswerResult:
    answer: str
    citations: tuple[Citation, ...]
    retrieval_count: int

    def __post_init__(self) -> None:
        if not self.answer.strip():
            raise ValueError("answer must not be empty")
        if self.retrieval_count < 0:
            raise ValueError("retrieval_count must not be negative")
        if len(self.citations) > self.retrieval_count:
            raise ValueError("citations cannot exceed retrieval_count")
