"""Evidence-grounded answer orchestration with application-built citations."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from html import escape
from time import monotonic
from typing import Final
from uuid import UUID

from app.domain.models import AnswerResult, Citation, RetrievalResult
from app.providers.llm_provider import INSUFFICIENT_EVIDENCE_MARKER, LLMProvider
from app.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)

NO_EVIDENCE_ANSWER: Final = (
    "I could not find enough evidence in the selected documents to answer this "
    "question."
)


class AnswerService:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        llm_provider: LLMProvider,
        citation_excerpt_limit: int = 240,
    ) -> None:
        if citation_excerpt_limit <= 0:
            raise ValueError("citation_excerpt_limit must be positive")
        self._retrieval_service = retrieval_service
        self._llm_provider = llm_provider
        self._citation_excerpt_limit = citation_excerpt_limit

    def answer(
        self,
        question: str,
        document_ids: Sequence[UUID],
        top_k: int,
        score_threshold: float | None = None,
    ) -> AnswerResult:
        started_at = monotonic()
        try:
            results = self._retrieval_service.search(
                query=question,
                document_ids=document_ids,
                top_k=top_k,
                score_threshold=score_threshold,
            )
            if not results:
                answer_result = AnswerResult(
                    answer=NO_EVIDENCE_ANSWER,
                    citations=(),
                    retrieval_count=0,
                )
            else:
                generated_answer = self._llm_provider.generate_answer(
                    question=question.strip(),
                    context_blocks=self._build_context_blocks(results),
                )
                if self._is_insufficient_evidence(generated_answer):
                    answer_result = AnswerResult(
                        answer=NO_EVIDENCE_ANSWER,
                        citations=(),
                        retrieval_count=len(results),
                    )
                else:
                    citations = tuple(
                        Citation.from_result(
                            result,
                            citation_number=index,
                            excerpt_limit=self._citation_excerpt_limit,
                        )
                        for index, result in enumerate(results, start=1)
                    )
                    answer_result = AnswerResult(
                        answer=generated_answer.strip(),
                        citations=citations,
                        retrieval_count=len(results),
                    )

            logger.info(
                "event=answer_succeeded provider=%s model=%s retrieval_count=%d "
                "citation_count=%d elapsed_ms=%d",
                self._llm_provider.name,
                self._llm_provider.model,
                answer_result.retrieval_count,
                len(answer_result.citations),
                int((monotonic() - started_at) * 1000),
            )
            return answer_result
        except Exception as exc:
            logger.warning(
                "event=answer_failed provider=%s model=%s error_type=%s elapsed_ms=%d",
                self._llm_provider.name,
                self._llm_provider.model,
                type(exc).__name__,
                int((monotonic() - started_at) * 1000),
            )
            raise

    @staticmethod
    def _build_context_blocks(results: Sequence[RetrievalResult]) -> list[str]:
        return [
            f'<source id="{index}">\n{escape(result.text, quote=False)}\n</source>'
            for index, result in enumerate(results, start=1)
        ]

    @staticmethod
    def _is_insufficient_evidence(answer: str) -> bool:
        return answer.strip().rstrip(".").upper() == INSUFFICIENT_EVIDENCE_MARKER
