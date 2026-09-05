from __future__ import annotations

import os
from pathlib import Path

import pytest

from evaluation.ingestion_benchmark import (
    IngestionBenchmarkConfig,
    run_ingestion_benchmark,
)

QDRANT_SERVER_URL = os.environ.get("RAG_TEST_QDRANT_URL")
PROJECT_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    not QDRANT_SERVER_URL,
    reason="RAG_TEST_QDRANT_URL is required for the R4 benchmark smoke test",
)


def test_short_r4_benchmark_exercises_server_and_independent_worker() -> None:
    assert QDRANT_SERVER_URL is not None
    report = run_ingestion_benchmark(
        PROJECT_ROOT,
        IngestionBenchmarkConfig(
            qdrant_url=QDRANT_SERVER_URL,
            quality_gate_evidence="current-ci-smoke",
            source_commit="test-worktree",
            document_size_bytes=1024,
            embedding_delay_ms=40,
            warmup_samples=0,
            single_samples=2,
            batch_rounds=1,
            batch_size=2,
            health_probes=1,
            poll_interval_ms=2,
            request_budget_ms=20,
            chunk_size=256,
            chunk_overlap=32,
            worker_timeout_seconds=30,
        ),
    )
    payload = report.to_dict()

    assert payload["benchmark"] == "r4-sync-async-ingestion"
    assert payload["synchronous"]["single"]["acceptance_ms"]["count"] == 2
    assert payload["asynchronous"]["single"]["acceptance_ms"]["count"] == 2
    assert payload["synchronous"]["responsiveness"]["status_codes"] == [200]
    assert payload["asynchronous"]["responsiveness"]["status_codes"] == [200]
    assert payload["crash_recovery"]["passed"] is True
    assert payload["crash_recovery"]["attempt_count"] == 2
    assert payload["environment"]["worker_boundary"] == (
        "independent-python-subprocess"
    )
    assert payload["limitations"]
