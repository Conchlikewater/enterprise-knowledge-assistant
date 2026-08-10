import json
from pathlib import Path

from evaluation.hybrid_experiment import run_hybrid_comparison

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_hybrid_comparison_uses_same_provider_and_complete_dataset() -> None:
    report = run_hybrid_comparison(PROJECT_ROOT)

    assert report.comparison_completed
    assert report.question_count == 50
    assert report.dense["strategy"] == "dense"
    assert report.hybrid["strategy"] == "hybrid-bm25-dense-rrf"
    assert (
        report.dense["profile"]["embedding_provider"]
        == report.hybrid["profile"]["embedding_provider"]
        == "offline-hashing"
    )
    assert report.hybrid["evidence_recall_at_k"] >= 0.0
    assert report.threshold_analysis["method"] == "offline-score-sweep"
    assert report.threshold_analysis["answerable_question_count"] == 40
    assert report.threshold_analysis["unanswerable_question_count"] == 8
    assert not report.production_change_recommended
    assert "hybrid_did_not_improve_evidence_recall" in report.decision_reasons
    assert report.hybrid["retrieval_bad_case_count"] >= 0
    assert (
        len(report.hybrid["retrieval_bad_cases"])
        == report.hybrid["retrieval_bad_case_count"]
    )


def test_tracked_hybrid_report_matches_reproducible_offline_run() -> None:
    generated = run_hybrid_comparison(PROJECT_ROOT).to_dict()
    tracked = json.loads(
        (PROJECT_ROOT / "evaluation" / "hybrid_report.json").read_text(encoding="utf-8")
    )

    assert generated == tracked
