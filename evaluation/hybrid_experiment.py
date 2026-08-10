"""Run a fair dense-versus-hybrid comparison on the tracked corpus."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from app.providers.embedding_provider import EmbeddingProvider
from app.services.retrieval_service import RetrievalService
from app.storage.sqlite_document_repository import SQLiteDocumentRepository
from app.storage.vector_store import VectorStore
from evaluation.hybrid import (
    BM25Retriever,
    HybridRetrievalService,
    RecordingVectorStore,
)
from evaluation.providers import HashingEmbeddingProvider
from evaluation.runner import (
    EmbeddingProviderFactory,
    EvaluationConfig,
    EvaluationReport,
    SearchService,
    run_evaluation,
)
from evaluation.thresholds import analyze_refusal_thresholds

HYBRID_EXPLORATORY_CONFIG = EvaluationConfig(
    name="hybrid-hashing-220-30-k5",
    unanswerable_score_threshold=0.0,
)


@dataclass(frozen=True, slots=True)
class HybridComparisonReport:
    """Serializable same-provider dense-versus-hybrid comparison."""

    comparison_completed: bool
    question_count: int
    dense: dict[str, Any]
    hybrid: dict[str, Any]
    delta_vs_dense: dict[str, float | int]
    threshold_analysis: dict[str, Any]
    production_change_recommended: bool
    decision_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["decision_reasons"] = list(self.decision_reasons)
        return payload


def run_hybrid_comparison(
    project_root: Path,
    embedding_provider_factory: EmbeddingProviderFactory = HashingEmbeddingProvider,
    *,
    dense_config: EvaluationConfig | None = None,
    hybrid_config: EvaluationConfig = HYBRID_EXPLORATORY_CONFIG,
) -> HybridComparisonReport:
    """Compare dense and hybrid retrieval with identical provider settings."""

    active_dense_config = dense_config or replace(
        hybrid_config,
        name=f"dense-control-for-{hybrid_config.name}",
    )
    dense_report = run_evaluation(
        project_root,
        config=active_dense_config,
        embedding_provider_factory=embedding_provider_factory,
    )
    hybrid_report = _run_hybrid_evaluation(
        project_root,
        config=hybrid_config,
        embedding_provider_factory=embedding_provider_factory,
    )
    if dense_report.question_count != hybrid_report.question_count:
        raise ValueError("dense and hybrid runs must use the same question count")
    if (
        dense_report.profile.embedding_provider
        != hybrid_report.profile.embedding_provider
        or dense_report.profile.embedding_dimensions
        != hybrid_report.profile.embedding_dimensions
    ):
        raise ValueError("dense and hybrid runs must use the same embedding provider")

    dense = _summary(dense_report, strategy="dense")
    hybrid = _summary(hybrid_report, strategy="hybrid-bm25-dense-rrf")
    threshold_analysis = analyze_refusal_thresholds(
        hybrid_report.question_results,
        minimum_threshold=hybrid_config.unanswerable_score_threshold,
    )
    delta_vs_dense = {
        "source_hit_rate_at_k": round(
            hybrid["source_hit_rate_at_k"] - dense["source_hit_rate_at_k"],
            4,
        ),
        "evidence_recall_at_k": round(
            hybrid["evidence_recall_at_k"] - dense["evidence_recall_at_k"],
            4,
        ),
        "evidence_mean_reciprocal_rank": round(
            hybrid["evidence_mean_reciprocal_rank"]
            - dense["evidence_mean_reciprocal_rank"],
            4,
        ),
        "retrieval_bad_case_count": (
            hybrid["retrieval_bad_case_count"] - dense["retrieval_bad_case_count"]
        ),
        "bad_case_count": hybrid["bad_case_count"] - dense["bad_case_count"],
    }
    recommended_threshold_metrics = threshold_analysis["recommended_metrics"]
    production_change_recommended = (
        delta_vs_dense["evidence_recall_at_k"] > 0
        and delta_vs_dense["evidence_mean_reciprocal_rank"] >= 0
        and recommended_threshold_metrics["unanswerable_rejection_rate"] >= 0.85
        and recommended_threshold_metrics["answerable_false_refusal_rate"] <= 0.05
    )
    decision_reasons = _decision_reasons(
        delta_vs_dense,
        recommended_threshold_metrics,
    )
    return HybridComparisonReport(
        comparison_completed=True,
        question_count=hybrid_report.question_count,
        dense=dense,
        hybrid=hybrid,
        delta_vs_dense=delta_vs_dense,
        threshold_analysis=threshold_analysis,
        production_change_recommended=production_change_recommended,
        decision_reasons=decision_reasons,
    )


def _run_hybrid_evaluation(
    project_root: Path,
    *,
    config: EvaluationConfig,
    embedding_provider_factory: EmbeddingProviderFactory,
) -> EvaluationReport:
    def wrap_vector_store(vector_store: VectorStore) -> RecordingVectorStore:
        return RecordingVectorStore(vector_store)

    def build_search_service(
        repository: SQLiteDocumentRepository,
        vector_store: VectorStore,
        embedding_provider: EmbeddingProvider,
    ) -> SearchService:
        if not isinstance(vector_store, RecordingVectorStore):
            raise TypeError("hybrid evaluation requires a recording vector store")
        dense_retriever = RetrievalService(
            document_repository=repository,
            vector_store=vector_store,
            embedding_provider=embedding_provider,
        )
        return HybridRetrievalService(
            dense_retriever,
            BM25Retriever(vector_store.chunks),
        )

    return run_evaluation(
        project_root,
        config=config,
        embedding_provider_factory=embedding_provider_factory,
        vector_store_wrapper=wrap_vector_store,
        search_service_factory=build_search_service,
    )


def _summary(report: EvaluationReport, *, strategy: str) -> dict[str, Any]:
    retrieval_bad_cases = [
        {
            "id": result["id"],
            "category": result["category"],
            "failures": result["failures"],
            "expected_evidence": result["expected_evidence"],
            "results": result["results"],
        }
        for result in report.question_results
        if result["expected_behavior"] == "answer" and not result["passed"]
    ]
    return {
        "strategy": strategy,
        "profile": asdict(report.profile),
        "quality_gates_passed_at_configured_threshold": report.passed,
        "source_hit_rate_at_k": report.source_hit_rate_at_k,
        "evidence_hit_rate_at_k": report.evidence_hit_rate_at_k,
        "evidence_recall_at_k": report.evidence_recall_at_k,
        "evidence_mean_reciprocal_rank": report.evidence_mean_reciprocal_rank,
        "unanswerable_rejection_rate": report.unanswerable_rejection_rate,
        "clarification_candidate_recall_at_k": (
            report.clarification_candidate_recall_at_k
        ),
        "retrieval_bad_case_count": len(retrieval_bad_cases),
        "retrieval_bad_case_ids": [case["id"] for case in retrieval_bad_cases],
        "retrieval_bad_cases": retrieval_bad_cases,
        "bad_case_count": report.bad_case_count,
        "bad_case_ids": [
            result["id"] for result in report.question_results if not result["passed"]
        ],
        "category_metrics": report.category_metrics,
    }


def _decision_reasons(
    delta: dict[str, float | int],
    threshold_metrics: dict[str, float],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if delta["evidence_recall_at_k"] <= 0:
        reasons.append("hybrid_did_not_improve_evidence_recall")
    if delta["evidence_mean_reciprocal_rank"] < 0:
        reasons.append("hybrid_reduced_mrr")
    if threshold_metrics["unanswerable_rejection_rate"] < 0.85:
        reasons.append("candidate_threshold_misses_refusal_gate")
    if threshold_metrics["answerable_false_refusal_rate"] > 0.05:
        reasons.append("candidate_threshold_rejects_too_many_answerable_questions")
    if not reasons:
        reasons.append("requires_real_semantic_provider_validation")
    return tuple(reasons)
