import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_tracked_semantic_hybrid_report_records_rejected_change() -> None:
    report = json.loads(
        (PROJECT_ROOT / "evaluation" / "semantic_hybrid_report.json").read_text(
            encoding="utf-8"
        )
    )

    assert report["comparison_completed"]
    assert report["question_count"] == 50
    assert report["dense"]["profile"]["embedding_model"] == ("text-embedding-3-small")
    assert report["hybrid"]["profile"]["embedding_model"] == ("text-embedding-3-small")
    assert report["dense"]["evidence_recall_at_k"] == 1.0
    assert report["hybrid"]["evidence_recall_at_k"] == 0.925
    assert report["dense"]["evidence_mean_reciprocal_rank"] == 0.9833
    assert report["hybrid"]["evidence_mean_reciprocal_rank"] == 0.8438
    assert report["hybrid"]["retrieval_bad_case_ids"] == [
        "paraphrase-05",
        "low-score-03",
        "low-score-04",
    ]
    assert not report["production_change_recommended"]
    assert report["decision_reasons"] == [
        "hybrid_did_not_improve_evidence_recall",
        "hybrid_reduced_mrr",
        "candidate_threshold_rejects_too_many_answerable_questions",
    ]
