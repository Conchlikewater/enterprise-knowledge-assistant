import json
from pathlib import Path

from evaluation.runner import run_evaluation

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_offline_evaluation_meets_every_quality_gate() -> None:
    report = run_evaluation(PROJECT_ROOT)

    assert report.passed, report.failed_checks
    assert report.ingested_document_count == 10
    assert report.question_count == 50
    assert report.profile.corpus == "tracked-synthetic-policy-corpus"
    assert report.profile.embedding_provider == "offline-hashing"
    assert report.profile.embedding_model is None
    assert report.profile.chunk_size == 220
    assert report.profile.chunk_overlap == 30
    assert report.profile.top_k == 5
    assert report.profile.answerable_score_threshold is None
    assert report.profile.unanswerable_score_threshold == 0.25
    assert report.source_hit_rate_at_k >= 0.80
    assert report.evidence_hit_rate_at_k >= report.profile.minimum_evidence_hit_rate
    assert report.evidence_recall_at_k >= report.profile.minimum_evidence_recall
    assert report.evidence_mean_reciprocal_rank >= report.profile.minimum_evidence_mrr
    assert report.multi_chunk_pass_rate == 1.0
    assert report.scope_isolation_pass_rate == 1.0
    assert (
        report.unanswerable_rejection_rate
        >= report.profile.minimum_unanswerable_rejection_rate
    )
    assert report.clarification_candidate_recall_at_k >= 0.0
    assert report.clarification_response_rate == 0.0
    assert report.citation_integrity_pass_rate == 1.0
    assert report.pdf_page_metadata_pass_rate == 1.0
    assert report.empty_chunk_invariant_passed
    assert report.deletion_passed
    assert report.bad_case_count > 0
    assert report.bad_case_count == sum(
        not result["passed"] for result in report.question_results
    )
    assert set(report.category_metrics) == {
        "direct",
        "multi_chunk",
        "scope_isolation",
        "unanswerable",
        "paraphrase",
        "distractor",
        "low_score",
        "ambiguous",
    }
    assert all(
        metrics["question_count"] > 0 for metrics in report.category_metrics.values()
    )

    answerable_results = [
        result for result in report.question_results if result["answerable"]
    ]
    assert answerable_results
    assert all(result["expected_evidence"] for result in answerable_results)
    assert all(result["evidence_hit_at_k"] is not None for result in answerable_results)
    assert all(
        item["rank"] == rank
        for result in report.question_results
        for rank, item in enumerate(result["results"], start=1)
    )
    assert all(
        "matched_evidence_numbers" in item
        for result in report.question_results
        for item in result["results"]
    )

    tracked_report = json.loads(
        (PROJECT_ROOT / "evaluation" / "latest_report.json").read_text(encoding="utf-8")
    )
    assert report.to_dict() == tracked_report
