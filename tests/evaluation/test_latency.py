from pathlib import Path

import pytest

from evaluation.latency import percentile, run_latency_benchmark

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_percentile_uses_linear_interpolation() -> None:
    values = [1.0, 2.0, 3.0, 4.0]

    assert percentile(values, 0.0) == 1.0
    assert percentile(values, 0.5) == 2.5
    assert percentile(values, 0.95) == pytest.approx(3.85)
    assert percentile(values, 1.0) == 4.0


@pytest.mark.parametrize(
    ("values", "percentile_value", "message"),
    [
        ([], 0.5, "values"),
        ([1.0], -0.1, "percentile_value"),
        ([1.0], 1.1, "percentile_value"),
    ],
)
def test_percentile_rejects_invalid_input(
    values: list[float],
    percentile_value: float,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        percentile(values, percentile_value)


def test_latency_benchmark_collects_post_warmup_samples() -> None:
    report = run_latency_benchmark(
        PROJECT_ROOT,
        rounds=1,
        warmup_questions_per_round=49,
    )

    assert report.measured_samples == 1
    assert report.profile["embedding_provider"] == "offline-hashing"
    assert report.retrieval_only_ms["p95"] >= report.retrieval_only_ms["p50"]
    assert report.answer_pipeline_ms["p95"] >= report.answer_pipeline_ms["p50"]
