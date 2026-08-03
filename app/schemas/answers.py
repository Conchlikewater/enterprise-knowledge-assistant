"""Public request and response models for grounded answers."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.domain.models import AnswerResult, Citation


class AnswerRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    document_ids: list[UUID] = Field(min_length=1, max_length=50)
    top_k: int = Field(default=5, ge=1, le=10)
    score_threshold: float | None = Field(default=None, ge=-1.0, le=1.0)

    @field_validator("question")
    @classmethod
    def question_must_contain_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question must contain non-whitespace text")
        return normalized

    @field_validator("document_ids")
    @classmethod
    def document_ids_must_be_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("document_ids must be unique")
        return value


class CitationResponse(BaseModel):
    citation_number: int = Field(ge=1)
    document_id: UUID
    chunk_id: UUID
    filename: str
    page_number: int | None = None
    excerpt: str
    score: float

    @classmethod
    def from_domain(cls, citation: Citation) -> CitationResponse:
        return cls(
            citation_number=citation.citation_number,
            document_id=citation.document_id,
            chunk_id=citation.chunk_id,
            filename=citation.filename,
            page_number=citation.page_number,
            excerpt=citation.excerpt,
            score=citation.score,
        )


class AnswerResponse(BaseModel):
    answer: str
    citations: list[CitationResponse]
    retrieval_count: int = Field(ge=0)

    @classmethod
    def from_domain(cls, result: AnswerResult) -> AnswerResponse:
        return cls(
            answer=result.answer,
            citations=[
                CitationResponse.from_domain(citation) for citation in result.citations
            ],
            retrieval_count=result.retrieval_count,
        )
