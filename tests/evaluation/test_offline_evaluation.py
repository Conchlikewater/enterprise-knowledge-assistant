import json
from pathlib import Path

from evaluation.runner import run_evaluation

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_offline_evaluation_meets_every_quality_gate() -> None:
    report = run_evaluation(PROJECT_ROOT)

    assert report.passed, report.failed_checks
    assert report.ingested_document_count == 10
    assert report.top5_source_accuracy >= 0.80
    assert report.multi_chunk_pass_rate == 1.0
    assert report.scope_isolation_pass_rate == 1.0
    assert report.unanswerable_rejection_rate == 1.0
    assert report.citation_integrity_pass_rate == 1.0
    assert report.pdf_page_metadata_pass_rate == 1.0
    assert report.empty_chunk_invariant_passed
    assert report.deletion_passed

    tracked_report = json.loads(
        (PROJECT_ROOT / "evaluation" / "latest_report.json").read_text(encoding="utf-8")
    )
    assert report.to_dict() == tracked_report
