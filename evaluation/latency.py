"""Dependency-free local latency benchmark for the evaluation pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil, floor
from pathlib import Path
from statistics import fmean
from typing import Any

from evaluation.contracts import EvaluationQuestion
from evaluation.runner import EvaluationConfig, run_evaluation


@dataclass(frozen=True, slots=True)
class LatencyBenchmarkReport:
    """Aggregate local timing measurements without unstable per-query output."""

    benchmark: str
    rounds: int
    warmup_questions_per_round: int
    measured_samples: int
    profile: dict[str, Any]
    retrieval_only_ms: dict[str, float]
    answer_pipeline_ms: dict[str, float]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["limitations"] = list(self.limitations)
        return payload


def run_latency_benchmark(
    project_root: Path,
    *,
    rounds: int = 3,
    warmup_questions_per_round: int = 5,
) -> LatencyBenchmarkReport:
    """Measure local retrieval and answer orchestration after a short warmup."""

    if rounds < 1:
        raise ValueError("rounds must be positive")
    if not 0 <= warmup_questions_per_round < 50:
        raise ValueError("warmup_questions_per_round must be between 0 and 49")

    retrieval_samples: list[float] = []
    answer_samples: list[float] = []
    profile: dict[str, Any] | None = None
    for round_number in range(1, rounds + 1):
        observed_questions = 0

        def observe(
            _question: EvaluationQuestion,
            retrieval_elapsed_ms: float,
            answer_elapsed_ms: float,
        ) -> None:
            nonlocal observed_questions
            observed_questions += 1
            if observed_questions <= warmup_questions_per_round:
                return
            retrieval_samples.append(retrieval_elapsed_ms)
            answer_samples.append(answer_elapsed_ms)

        report = run_evaluation(
            project_root,
            config=EvaluationConfig(name=f"latency-round-{round_number}"),
            question_timing_observer=observe,
        )
        if not report.passed:
            raise RuntimeError("latency benchmark quality gate failed")
        if observed_questions != report.question_count:
            raise RuntimeError("latency observer missed evaluation questions")
        if profile is None:
            profile = {
                "embedding_provider": report.profile.embedding_provider,
                "embedding_dimensions": report.profile.embedding_dimensions,
                "vector_store": "qdrant-local-temporary",
                "llm_provider": report.profile.llm_provider,
                "chunk_size": report.profile.chunk_size,
                "chunk_overlap": report.profile.chunk_overlap,
                "top_k": report.profile.top_k,
            }

    expected_samples = rounds * (50 - warmup_questions_per_round)
    if len(retrieval_samples) != expected_samples or len(answer_samples) != (
        expected_samples
    ):
        raise RuntimeError("latency sample count is inconsistent")
    return LatencyBenchmarkReport(
        benchmark="offline-local-request-latency",
        rounds=rounds,
        warmup_questions_per_round=warmup_questions_per_round,
        measured_samples=expected_samples,
        profile=profile or {},
        retrieval_only_ms=_summarize(retrieval_samples),
        answer_pipeline_ms=_summarize(answer_samples),
        limitations=(
            "Uses deterministic hashing embeddings rather than a network API.",
            "Uses temporary local Qdrant and SQLite stores with a synthetic corpus.",
            "Answer timing uses the deterministic evaluation LLM provider.",
            "Results describe this machine and workload, not production capacity.",
        ),
    )


def percentile(values: list[float], percentile_value: float) -> float:
    """Return a linearly interpolated percentile for non-empty numeric values."""

    if not values:
        raise ValueError("values must not be empty")
    if not 0.0 <= percentile_value <= 1.0:
        raise ValueError("percentile_value must be between 0 and 1")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile_value
    lower_index = floor(position)
    upper_index = ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    weight = position - lower_index
    return ordered[lower_index] * (1.0 - weight) + ordered[upper_index] * weight


def _summarize(values: list[float]) -> dict[str, float]:
    return {
        "mean": round(fmean(values), 4),
        "p50": round(percentile(values, 0.50), 4),
        "p95": round(percentile(values, 0.95), 4),
        "minimum": round(min(values), 4),
        "maximum": round(max(values), 4),
    }
