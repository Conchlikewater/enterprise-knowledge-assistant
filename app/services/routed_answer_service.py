"""Bounded R6 route, retrieve, optionally rewrite once, and answer orchestration."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from math import isfinite
from time import monotonic
from typing import Final
from uuid import UUID

from app.core.exceptions import ProviderConfigurationError
from app.domain.models import (
    AnswerResult,
    AnswerRoute,
    RetrievalResult,
    RoutedAnswerResult,
    RouteReason,
    RoutingDecision,
    RoutingStopReason,
)
from app.services.answer_service import NO_EVIDENCE_ANSWER, AnswerService
from app.services.evidence_sufficiency import EvidenceSufficiencyPolicy
from app.services.query_rewriter import RuleBasedQueryRewriter
from app.services.question_router import RuleBasedQuestionRouter
from app.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)

DIRECT_ANSWERS_EN: Final = {
    RouteReason.GREETING: (
        "Hello. I can help you search and answer questions from documents you select."
    ),
    RouteReason.CAPABILITY_HELP: (
        "I can search selected TXT or PDF documents, answer from retrieved evidence, "
        "and return source citations. I do not use conversation memory or outside "
        "knowledge for document facts."
    ),
    RouteReason.USAGE_HELP: (
        "Upload a TXT or text-based PDF, wait until it is ready, select its document "
        "ID, and then ask a question. Use the returned filename, page, chunk, and "
        "excerpt to inspect each citation."
    ),
}
DIRECT_ANSWERS_ZH: Final = {
    RouteReason.GREETING: "你好。我可以基于你选择的文档检索证据并回答问题。",
    RouteReason.CAPABILITY_HELP: (
        "我可以检索你选择的 TXT 或 PDF 文档，基于证据回答并返回来源引用。"
        "我不会用对话记忆或模型常识绕开文档回答业务事实。"
    ),
    RouteReason.USAGE_HELP: (
        "先上传 TXT 或可提取文本的 PDF，等待文档就绪，再选择 document_id 提问。"
        "可以通过返回的文件名、页码、chunk_id 和原文摘录核对 Citation。"
    ),
}
REFUSAL_EN: Final = (
    "I cannot bypass document evidence, reveal secrets, cross the selected document "
    "scope, or perform that unsupported action."
)
REFUSAL_ZH: Final = "我不能绕过文档证据、泄露秘密、越过所选文档范围或执行该未授权操作。"


class RoutedAnswerService:
    def __init__(
        self,
        retrieval_service: RetrievalService | None,
        answer_service: AnswerService | None,
        *,
        question_router: RuleBasedQuestionRouter | None = None,
        query_rewriter: RuleBasedQueryRewriter | None = None,
        evidence_policy: EvidenceSufficiencyPolicy | None = None,
        max_top_k: int = 5,
    ) -> None:
        if max_top_k <= 0:
            raise ValueError("max_top_k must be positive")
        self._retrieval_service = retrieval_service
        self._answer_service = answer_service
        self._question_router = question_router or RuleBasedQuestionRouter()
        self._query_rewriter = query_rewriter or RuleBasedQueryRewriter()
        self._evidence_policy = evidence_policy or EvidenceSufficiencyPolicy()
        self._max_top_k = max_top_k

    def answer(
        self,
        question: str,
        document_ids: Sequence[UUID],
        top_k: int = 5,
        score_threshold: float | None = None,
    ) -> RoutedAnswerResult:
        started_at = monotonic()
        normalized_question, selected_ids = self._validate_request(
            question,
            document_ids,
            top_k,
            score_threshold,
        )
        decision = self._question_router.route(normalized_question)
        result = self._execute(
            normalized_question,
            selected_ids,
            top_k,
            score_threshold,
            decision,
        )
        logger.info(
            "event=routed_answer_succeeded route=%s route_reason=%s "
            "retrieval_attempts=%d retrieval_count=%d stop_reason=%s elapsed_ms=%d",
            result.route,
            result.route_reason,
            result.retrieval_attempts,
            result.retrieval_count,
            result.stop_reason,
            int((monotonic() - started_at) * 1000),
        )
        return result

    def _execute(
        self,
        question: str,
        document_ids: tuple[UUID, ...],
        top_k: int,
        score_threshold: float | None,
        decision: RoutingDecision,
    ) -> RoutedAnswerResult:
        if decision.route is AnswerRoute.DIRECT_ANSWER:
            return self._direct_answer(question, decision)
        if decision.route is AnswerRoute.REFUSE:
            return self._refuse(question, decision)
        if not document_ids:
            return self._no_evidence(
                decision,
                retrieval_count=0,
                retrieval_attempts=0,
                stop_reason=RoutingStopReason.NO_DOCUMENT_SCOPE,
            )

        retrieval_service, answer_service = self._runtime_services()
        first_results = self._ordered_unique(
            retrieval_service.search(
                query=question,
                document_ids=document_ids,
                top_k=top_k,
                score_threshold=score_threshold,
            ),
            limit=top_k,
        )
        first_assessment = self._evidence_policy.assess(
            first_results,
            top_k=top_k,
            score_threshold=score_threshold,
        )
        if not first_assessment.should_retry:
            return self._generate(
                answer_service,
                question,
                first_results,
                decision,
                retrieval_attempts=1,
                rewritten_query=None,
                success_stop=RoutingStopReason.SUFFICIENT_EVIDENCE_FIRST_PASS,
            )

        rewritten_query = self._query_rewriter.rewrite(question)
        if rewritten_query is None:
            return self._no_evidence(
                decision,
                retrieval_count=len(first_results),
                retrieval_attempts=1,
                stop_reason=RoutingStopReason.NO_SAFE_REWRITE,
            )

        second_results = self._ordered_unique(
            retrieval_service.search(
                query=rewritten_query,
                document_ids=document_ids,
                top_k=top_k,
                score_threshold=score_threshold,
            ),
            limit=top_k,
        )
        merged_results = self._merge_rounds(first_results, second_results)
        final_assessment = self._evidence_policy.assess(
            merged_results,
            top_k=top_k,
            score_threshold=score_threshold,
        )
        if final_assessment.should_retry:
            return self._no_evidence(
                decision,
                retrieval_count=len(merged_results),
                retrieval_attempts=2,
                rewritten_query=rewritten_query,
                stop_reason=RoutingStopReason.RETRY_EXHAUSTED,
            )
        return self._generate(
            answer_service,
            question,
            merged_results,
            decision,
            retrieval_attempts=2,
            rewritten_query=rewritten_query,
            success_stop=RoutingStopReason.RETRY_SUCCEEDED,
        )

    @staticmethod
    def _generate(
        answer_service: AnswerService,
        question: str,
        results: Sequence[RetrievalResult],
        decision: RoutingDecision,
        *,
        retrieval_attempts: int,
        rewritten_query: str | None,
        success_stop: RoutingStopReason,
    ) -> RoutedAnswerResult:
        answer_result = answer_service.answer_from_evidence(question, results)
        stop_reason = (
            RoutingStopReason.GENERATOR_REFUSAL
            if not answer_result.citations
            else success_stop
        )
        return RoutedAnswerService._from_answer_result(
            answer_result,
            decision,
            retrieval_attempts=retrieval_attempts,
            rewritten_query=rewritten_query,
            stop_reason=stop_reason,
        )

    @staticmethod
    def _from_answer_result(
        answer_result: AnswerResult,
        decision: RoutingDecision,
        *,
        retrieval_attempts: int,
        rewritten_query: str | None,
        stop_reason: RoutingStopReason,
    ) -> RoutedAnswerResult:
        return RoutedAnswerResult(
            answer=answer_result.answer,
            citations=answer_result.citations,
            retrieval_count=answer_result.retrieval_count,
            route=decision.route,
            route_reason=decision.reason,
            retrieval_attempts=retrieval_attempts,
            rewritten_query=rewritten_query,
            stop_reason=stop_reason,
        )

    @staticmethod
    def _no_evidence(
        decision: RoutingDecision,
        *,
        retrieval_count: int,
        retrieval_attempts: int,
        stop_reason: RoutingStopReason,
        rewritten_query: str | None = None,
    ) -> RoutedAnswerResult:
        return RoutedAnswerResult(
            answer=NO_EVIDENCE_ANSWER,
            citations=(),
            retrieval_count=retrieval_count,
            route=decision.route,
            route_reason=decision.reason,
            retrieval_attempts=retrieval_attempts,
            rewritten_query=rewritten_query,
            stop_reason=stop_reason,
        )

    @staticmethod
    def _direct_answer(question: str, decision: RoutingDecision) -> RoutedAnswerResult:
        answers = DIRECT_ANSWERS_ZH if _contains_cjk(question) else DIRECT_ANSWERS_EN
        return RoutedAnswerResult(
            answer=answers[decision.reason],
            citations=(),
            retrieval_count=0,
            route=decision.route,
            route_reason=decision.reason,
            retrieval_attempts=0,
            stop_reason=RoutingStopReason.DIRECT_ANSWER,
        )

    @staticmethod
    def _refuse(question: str, decision: RoutingDecision) -> RoutedAnswerResult:
        return RoutedAnswerResult(
            answer=REFUSAL_ZH if _contains_cjk(question) else REFUSAL_EN,
            citations=(),
            retrieval_count=0,
            route=decision.route,
            route_reason=decision.reason,
            retrieval_attempts=0,
            stop_reason=RoutingStopReason.ROUTER_REFUSAL,
        )

    def _runtime_services(self) -> tuple[RetrievalService, AnswerService]:
        if self._retrieval_service is None or self._answer_service is None:
            raise ProviderConfigurationError()
        return self._retrieval_service, self._answer_service

    def _validate_request(
        self,
        question: str,
        document_ids: Sequence[UUID],
        top_k: int,
        score_threshold: float | None,
    ) -> tuple[str, tuple[UUID, ...]]:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must not be empty")
        if not 1 <= top_k <= self._max_top_k:
            raise ValueError("top_k is outside the supported range")
        if score_threshold is not None and (
            not isfinite(score_threshold) or not -1.0 <= score_threshold <= 1.0
        ):
            raise ValueError("score_threshold must be between -1 and 1")
        selected_ids = tuple(document_ids)
        if len(set(selected_ids)) != len(selected_ids):
            raise ValueError("document_ids must be unique")
        return question.strip(), selected_ids

    @staticmethod
    def _ordered_unique(
        results: Sequence[RetrievalResult],
        *,
        limit: int,
    ) -> list[RetrievalResult]:
        ordered = sorted(results, key=lambda item: (-item.score, str(item.chunk_id)))
        unique: list[RetrievalResult] = []
        seen = set()
        for result in ordered[:limit]:
            if result.chunk_id not in seen:
                unique.append(result)
                seen.add(result.chunk_id)
        return unique

    @staticmethod
    def _merge_rounds(
        first_results: Sequence[RetrievalResult],
        second_results: Sequence[RetrievalResult],
    ) -> list[RetrievalResult]:
        merged: list[RetrievalResult] = []
        seen = set()
        for result in (*first_results, *second_results):
            if result.chunk_id not in seen:
                merged.append(result)
                seen.add(result.chunk_id)
        return merged


def _contains_cjk(text: str) -> bool:
    return re.search(r"[\u4e00-\u9fff]", text) is not None
