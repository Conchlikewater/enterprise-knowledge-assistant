"""Compare the tracked lexical baseline with one semantic embedding run."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from evaluation.providers import CachingEmbeddingProvider
from evaluation.runner import (
    EmbeddingProviderFactory,
    EvaluationConfig,
    EvaluationReport,
    run_evaluation,
)
from evaluation.thresholds import analyze_refusal_thresholds

SEMANTIC_CONFIG = EvaluationConfig(name="semantic-openai-220-30-k5")


@dataclass(frozen=True, slots=True)
class SemanticComparisonReport:
    """Serializable baseline-versus-semantic retrieval comparison."""

    comparison_completed: bool
    question_count: int
    baseline: dict[str, Any]
    semantic: dict[str, Any]
    delta_vs_baseline: dict[str, float | int]
    threshold_analysis: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_semantic_comparison(
    project_root: Path,
    embedding_provider_factory: EmbeddingProviderFactory,
    *,
    config: EvaluationConfig = SEMANTIC_CONFIG,
) -> SemanticComparisonReport:
    """Run a semantic evaluation without using the production data stores."""

    baseline_path = project_root / "evaluation" / "latest_report.json"
    baseline_report = json.loads(baseline_path.read_text(encoding="utf-8"))

    def cached_provider_factory() -> CachingEmbeddingProvider:
        return CachingEmbeddingProvider(embedding_provider_factory())

    semantic_report = run_evaluation(
        project_root,
        config=config,
        embedding_provider_factory=cached_provider_factory,
    )
    if semantic_report.question_count != baseline_report["question_count"]:
        raise ValueError("baseline and semantic runs must use the same question count")

    baseline = _summary(baseline_report)
    semantic = _summary(semantic_report)
    return SemanticComparisonReport(
        comparison_completed=True,
        question_count=semantic_report.question_count,
        baseline=baseline,
        semantic=semantic,
        delta_vs_baseline={
            "source_hit_rate_at_k": round(
                semantic["source_hit_rate_at_k"] - baseline["source_hit_rate_at_k"],
                4,
            ),
            "evidence_recall_at_k": round(
                semantic["evidence_recall_at_k"] - baseline["evidence_recall_at_k"],
                4,
            ),
            "evidence_mean_reciprocal_rank": round(
                semantic["evidence_mean_reciprocal_rank"]
                - baseline["evidence_mean_reciprocal_rank"],
                4,
            ),
            "unanswerable_rejection_rate": round(
                semantic["unanswerable_rejection_rate"]
                - baseline["unanswerable_rejection_rate"],
                4,
            ),
            "bad_case_count": semantic["bad_case_count"] - baseline["bad_case_count"],
        },
        threshold_analysis=analyze_refusal_thresholds(
            semantic_report.question_results,
            minimum_threshold=config.unanswerable_score_threshold,
        ),
    )


def _summary(report: EvaluationReport | dict[str, Any]) -> dict[str, Any]:
    payload = report.to_dict() if isinstance(report, EvaluationReport) else report
    return {
        "profile": payload["profile"],
        "quality_gates_passed": payload["passed"],
        "source_hit_rate_at_k": payload["source_hit_rate_at_k"],
        "evidence_hit_rate_at_k": payload["evidence_hit_rate_at_k"],
        "evidence_recall_at_k": payload["evidence_recall_at_k"],
        "evidence_mean_reciprocal_rank": payload["evidence_mean_reciprocal_rank"],
        "unanswerable_rejection_rate": payload["unanswerable_rejection_rate"],
        "clarification_candidate_recall_at_k": payload[
            "clarification_candidate_recall_at_k"
        ],
        "bad_case_count": payload["bad_case_count"],
        "bad_case_ids": [
            result["id"]
            for result in payload["question_results"]
            if not result["passed"]
        ],
        "category_metrics": payload["category_metrics"],
    }
