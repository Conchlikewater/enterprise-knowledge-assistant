"""Public request and response models for document-scoped retrieval."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.domain.models import RetrievalResult


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    document_ids: list[UUID] = Field(min_length=1, max_length=50)
    top_k: int = Field(default=5, ge=1, le=50)
    score_threshold: float | None = Field(default=None, ge=-1.0, le=1.0)

    @field_validator("query")
    @classmethod
    def query_must_contain_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must contain non-whitespace text")
        return normalized

    @field_validator("document_ids")
    @classmethod
    def document_ids_must_be_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("document_ids must be unique")
        return value


class RetrievalResultResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    page_number: int | None = None
    text: str
    score: float

    @classmethod
    def from_domain(cls, result: RetrievalResult) -> RetrievalResultResponse:
        return cls(
            chunk_id=result.chunk_id,
            document_id=result.document_id,
            filename=result.filename,
            page_number=result.page_number,
            text=result.text,
            score=result.score,
        )


class SearchResponse(BaseModel):
    results: list[RetrievalResultResponse]
    count: int = Field(ge=0)
    searched_document_ids: list[UUID]
