"""Reproducible isolated comparisons; preserve the legacy experiment imports."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from evaluation.runner import EvaluationConfig, run_evaluation

DEFAULT_EXPERIMENT_CONFIGS = (
    EvaluationConfig(name="baseline-220-30-k5"),
    EvaluationConfig(name="small-160-30-k5", chunk_size=160, chunk_overlap=30),
    EvaluationConfig(name="large-320-50-k5", chunk_size=320, chunk_overlap=50),
    EvaluationConfig(name="baseline-220-30-k3", top_k=3),
    EvaluationConfig(name="baseline-220-30-k10", top_k=10),
)


@dataclass(frozen=True, slots=True)
class ExperimentReport:
    """Compact comparison report for a set of evaluation profiles."""

    profile_count: int
    question_count: int
    all_runs_completed: bool
    profiles: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["profiles"] = list(self.profiles)
        return payload


def run_experiments(
    project_root: Path | None = None,
    configs: tuple[EvaluationConfig, ...] = DEFAULT_EXPERIMENT_CONFIGS,
) -> ExperimentReport:
    """Run every profile with a fresh temporary SQLite and Qdrant store."""

    if not configs:
        raise ValueError("at least one experiment config is required")
    names = [config.name for config in configs]
    if len(names) != len(set(names)):
        raise ValueError("experiment config names must be unique")

    profile_summaries: list[dict[str, Any]] = []
    question_count: int | None = None
    baseline_summary: dict[str, Any] | None = None
    for config in configs:
        report = run_evaluation(project_root, config=config)
        question_count = report.question_count
        summary = {
            "name": config.name,
            "profile": asdict(report.profile),
            "quality_gates_passed": report.passed,
            "source_hit_rate_at_k": report.source_hit_rate_at_k,
            "evidence_hit_rate_at_k": report.evidence_hit_rate_at_k,
            "evidence_recall_at_k": report.evidence_recall_at_k,
            "evidence_mean_reciprocal_rank": (report.evidence_mean_reciprocal_rank),
            "unanswerable_rejection_rate": report.unanswerable_rejection_rate,
            "clarification_candidate_recall_at_k": (
                report.clarification_candidate_recall_at_k
            ),
            "clarification_response_rate": report.clarification_response_rate,
            "bad_case_count": report.bad_case_count,
            "bad_case_ids": [
                result["id"]
                for result in report.question_results
                if not result["passed"]
            ],
            "category_metrics": report.category_metrics,
            "clarification_cases": [
                {
                    "id": result["id"],
                    "candidate_recall_at_k": result["evidence_recall_at_k"],
                    "top_score_gap": result["top_score_gap"],
                    "near_top_candidate_count": result["near_top_candidate_count"],
                    "results": result["results"],
                }
                for result in report.question_results
                if result["expected_behavior"] == "clarify"
            ],
        }
        if baseline_summary is None:
            baseline_summary = summary
        summary["delta_vs_baseline"] = _delta_vs_baseline(summary, baseline_summary)
        profile_summaries.append(summary)

    return ExperimentReport(
        profile_count=len(profile_summaries),
        question_count=question_count or 0,
        all_runs_completed=True,
        profiles=tuple(profile_summaries),
    )


def _delta_vs_baseline(
    summary: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, float | int]:
    return {
        "source_hit_rate_at_k": round(
            summary["source_hit_rate_at_k"] - baseline["source_hit_rate_at_k"],
            4,
        ),
        "evidence_recall_at_k": round(
            summary["evidence_recall_at_k"] - baseline["evidence_recall_at_k"],
            4,
        ),
        "evidence_mean_reciprocal_rank": round(
            summary["evidence_mean_reciprocal_rank"]
            - baseline["evidence_mean_reciprocal_rank"],
            4,
        ),
        "bad_case_count": summary["bad_case_count"] - baseline["bad_case_count"],
    }
