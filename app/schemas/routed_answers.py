"""Public V2 schemas for bounded routed answers."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.domain.models import (
    AnswerRoute,
    RoutedAnswerResult,
    RouteReason,
    RoutingStopReason,
)
from app.schemas.answers import CitationResponse


class RoutedAnswerRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    document_ids: list[UUID] = Field(default_factory=list, max_length=50)
    top_k: int = Field(default=5, ge=1, le=5)
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


class RoutedAnswerResponse(BaseModel):
    answer: str
    citations: list[CitationResponse]
    retrieval_count: int = Field(ge=0)
    route: AnswerRoute
    route_reason: RouteReason
    retrieval_attempts: int = Field(ge=0, le=2)
    rewritten_query: str | None = None
    stop_reason: RoutingStopReason

    @classmethod
    def from_domain(cls, result: RoutedAnswerResult) -> RoutedAnswerResponse:
        return cls(
            answer=result.answer,
            citations=[
                CitationResponse.from_domain(citation) for citation in result.citations
            ],
            retrieval_count=result.retrieval_count,
            route=result.route,
            route_reason=result.route_reason,
            retrieval_attempts=result.retrieval_attempts,
            rewritten_query=result.rewritten_query,
            stop_reason=result.stop_reason,
        )
