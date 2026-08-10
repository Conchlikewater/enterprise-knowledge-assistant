import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_tracked_latency_report_has_valid_local_percentiles() -> None:
    report = json.loads(
        (PROJECT_ROOT / "evaluation" / "latency_report.json").read_text(
            encoding="utf-8"
        )
    )

    assert report["benchmark"] == "offline-local-request-latency"
    assert report["rounds"] == 3
    assert report["measured_samples"] == 135
    assert report["profile"]["embedding_provider"] == "offline-hashing"
    assert report["retrieval_only_ms"]["p95"] >= report["retrieval_only_ms"]["p50"]
    assert report["answer_pipeline_ms"]["p95"] >= report["answer_pipeline_ms"]["p50"]
    assert report["limitations"]
