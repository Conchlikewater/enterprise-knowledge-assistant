import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_tracked_semantic_report_records_improvement_and_tradeoff() -> None:
    report = json.loads(
        (PROJECT_ROOT / "evaluation" / "semantic_report.json").read_text(
            encoding="utf-8"
        )
    )

    assert report["comparison_completed"]
    assert report["question_count"] == 50
    assert report["semantic"]["profile"]["embedding_provider"] == "openai"
    assert report["semantic"]["profile"]["embedding_model"] == "text-embedding-3-small"
    assert report["semantic"]["evidence_recall_at_k"] == 1.0
    assert report["semantic"]["evidence_mean_reciprocal_rank"] == 0.9833
    assert report["delta_vs_baseline"]["evidence_recall_at_k"] == 0.175
    assert report["delta_vs_baseline"]["unanswerable_rejection_rate"] == -0.375
    assert not report["semantic"]["quality_gates_passed"]
    assert set(report["semantic"]["bad_case_ids"]) == {
        "unanswerable-02",
        "unanswerable-04",
        "unanswerable-06",
        "unanswerable-07",
        "ambiguous-01",
        "ambiguous-02",
    }

    threshold_analysis = report["threshold_analysis"]
    assert threshold_analysis["recommended_threshold_on_this_dataset"] == 0.37
    assert threshold_analysis["recommended_metrics"] == {
        "threshold": 0.37,
        "evidence_hit_rate": 1.0,
        "evidence_recall": 1.0,
        "answerable_retention_rate": 1.0,
        "answerable_false_refusal_rate": 0.0,
        "unanswerable_rejection_rate": 1.0,
        "balanced_score": 1.0,
    }
    perfect_thresholds = [
        row["threshold"]
        for row in threshold_analysis["sweep"]
        if row["evidence_recall"] == 1.0
        and row["unanswerable_rejection_rate"] == 1.0
        and row["answerable_false_refusal_rate"] == 0.0
    ]
    assert perfect_thresholds == [0.37, 0.38, 0.39, 0.4, 0.41]
