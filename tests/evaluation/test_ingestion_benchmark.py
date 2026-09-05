from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from evaluation import ingestion_benchmark as benchmark_module
from evaluation.ingestion_benchmark import (
    IngestionBenchmarkConfig,
    evaluate_demo_decision,
    summarize_timings,
)


def test_timing_summary_uses_the_shared_percentile_rule() -> None:
    summary = summarize_timings([1.0, 2.0, 3.0, 4.0])

    assert summary.count == 4
    assert summary.mean_ms == 2.5
    assert summary.p50_ms == 2.5
    assert summary.p95_ms == 3.85
    assert summary.minimum_ms == 1.0
    assert summary.maximum_ms == 4.0


def test_demo_decision_requires_every_preregistered_condition() -> None:
    eligible = evaluate_demo_decision(
        sync_acceptance_p95_ms=220,
        async_acceptance_p95_ms=20,
        sync_batch_response_p95_ms=1100,
        async_batch_response_p95_ms=80,
        request_budget_ms=100,
        crash_recovery_passed=True,
        quality_gate_evidence="ci:123",
    )
    missing_recovery = evaluate_demo_decision(
        sync_acceptance_p95_ms=220,
        async_acceptance_p95_ms=20,
        sync_batch_response_p95_ms=1100,
        async_batch_response_p95_ms=80,
        request_budget_ms=100,
        crash_recovery_passed=False,
        quality_gate_evidence="ci:123",
    )

    assert eligible["eligible"] is True
    assert eligible["recommendation"].startswith("prefer_v2")
    assert missing_recovery["eligible"] is False
    assert missing_recovery["recommendation"].startswith("retain_both")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"qdrant_url": "https://example.com:6333"}, "loopback"),
        ({"quality_gate_evidence": " "}, "quality_gate_evidence"),
        ({"single_samples": 0}, "single_samples"),
        ({"warmup_samples": -1}, "warmup_samples"),
        ({"chunk_overlap": 1000}, "chunk_overlap"),
    ],
)
def test_benchmark_config_rejects_unsafe_or_invalid_values(
    overrides: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "qdrant_url": "http://127.0.0.1:6333",
        "quality_gate_evidence": "ci:test",
        "source_commit": "abc123",
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        IngestionBenchmarkConfig(**values)


def test_long_running_worker_uses_a_file_instead_of_a_pipe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeProcess:
        returncode = 0

        def poll(self) -> int:
            return 0

    def fake_popen(*args: object, **kwargs: object) -> FakeProcess:
        captured.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(benchmark_module.subprocess, "Popen", fake_popen)
    config = IngestionBenchmarkConfig(
        qdrant_url="http://127.0.0.1:6333",
        quality_gate_evidence="ci:test",
        source_commit="abc123",
    )

    worker = benchmark_module._start_worker_process(
        tmp_path,
        mode="serve",
        root=tmp_path,
        collection="test_collection",
        config=config,
        max_jobs=1,
    )

    assert captured["stdout"] is worker.log_stream
    assert captured["stdout"] is not subprocess.PIPE
    assert captured["stderr"] is subprocess.STDOUT
    assert worker.log_path == tmp_path / "worker-process.log"

    benchmark_module._terminate_worker(worker)
    assert worker.log_stream.closed is True
