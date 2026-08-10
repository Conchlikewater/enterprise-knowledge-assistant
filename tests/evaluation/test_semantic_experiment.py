from pathlib import Path

from evaluation.providers import HashingEmbeddingProvider
from evaluation.semantic_experiment import run_semantic_comparison

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class _NamedHashingProvider(HashingEmbeddingProvider):
    @property
    def name(self) -> str:
        return "semantic-test-double"

    @property
    def model(self) -> str:
        return "deterministic-test-model"


def test_semantic_comparison_uses_injected_provider_and_tracked_baseline() -> None:
    report = run_semantic_comparison(PROJECT_ROOT, _NamedHashingProvider)

    assert report.comparison_completed
    assert report.question_count == 50
    assert report.semantic["profile"]["embedding_provider"] == "semantic-test-double"
    assert report.semantic["profile"]["embedding_model"] == "deterministic-test-model"
    assert report.delta_vs_baseline["evidence_recall_at_k"] == 0.0
    assert report.delta_vs_baseline["evidence_mean_reciprocal_rank"] == 0.0
    assert report.delta_vs_baseline["bad_case_count"] == 0
    assert report.threshold_analysis["method"] == "offline-score-sweep"
    assert report.threshold_analysis["answerable_question_count"] == 40
    assert report.threshold_analysis["unanswerable_question_count"] == 8
