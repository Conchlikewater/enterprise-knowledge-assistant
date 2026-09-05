from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = PROJECT_ROOT / "evaluation" / "ingestion_benchmark_report.json"


def test_r4_report_preserves_the_preregistered_samples_and_decision() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    synchronous = report["synchronous"]
    asynchronous = report["asynchronous"]
    crash = report["crash_recovery"]

    assert report["benchmark"] == "r4-sync-async-ingestion"
    assert report["schema_version"] == 1
    assert len(report["source_commit"]) == 40
    assert report["quality_gate_evidence"].startswith("github-actions:")

    assert synchronous["single"]["acceptance_ms"]["count"] == 20
    assert asynchronous["single"]["acceptance_ms"]["count"] == 20
    assert len(synchronous["single"]["raw_acceptance_ms"]) == 20
    assert len(asynchronous["single"]["raw_acceptance_ms"]) == 20
    assert synchronous["sequential_batch"]["rounds"] == 3
    assert asynchronous["sequential_batch"]["documents_per_round"] == 5

    assert (
        asynchronous["single"]["acceptance_ms"]["p95_ms"]
        < synchronous["single"]["acceptance_ms"]["p95_ms"]
    )
    assert (
        asynchronous["single"]["end_to_end_ms"]["p95_ms"]
        > synchronous["single"]["end_to_end_ms"]["p95_ms"]
    )
    assert (
        asynchronous["sequential_batch"]["all_responses_ms"]["p95_ms"]
        < synchronous["sequential_batch"]["all_responses_ms"]["p95_ms"]
    )
    assert (
        asynchronous["sequential_batch"]["all_ready_ms"]["p95_ms"]
        > synchronous["sequential_batch"]["all_ready_ms"]["p95_ms"]
    )

    assert synchronous["request_budget"]["acceptance_p95_exceeds_budget"] is True
    assert asynchronous["request_budget"]["acceptance_p95_exceeds_budget"] is False
    assert crash["passed"] is True
    assert crash["attempt_count"] == 2
    assert crash["visible_chunk_count"] == crash["unique_visible_chunk_count"]
    assert report["decision"]["eligible"] is True
    assert report["decision"]["scope"].startswith("portfolio demonstration only")
    assert len(report["limitations"]) >= 6


def test_r4_human_readable_documents_match_the_machine_report() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    analysis = (PROJECT_ROOT / "docs" / "r4_sync_async_evaluation.md").read_text(
        encoding="utf-8"
    )
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert report["source_commit"] in analysis
    assert report["quality_gate_evidence"].removeprefix("github-actions:") in analysis
    for expected_value in ("340.65", "49.32", "775.81", "1559.06", "3192.49"):
        assert expected_value in analysis
        assert expected_value in readme
