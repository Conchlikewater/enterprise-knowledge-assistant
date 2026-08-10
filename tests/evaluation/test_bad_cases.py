import json
from pathlib import Path

from evaluation.bad_cases import build_bad_case_report

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_bad_case_report_groups_failures_by_stage_and_decision() -> None:
    report = build_bad_case_report(PROJECT_ROOT)
    groups = {group.name: group for group in report.groups}

    assert groups["hashing_answerable_retrieval_misses"].count == 7
    assert groups["hashing_refusal_false_accepts"].count == 1
    assert groups["semantic_refusal_false_accepts_at_old_threshold"].count == 4
    assert groups["clarification_response_not_supported"].count == 2
    assert groups["semantic_hybrid_regressions"].count == 3
    assert not report.decisions["hybrid_promoted"]
    assert report.decisions["retrieval_strategy"] == "semantic-dense"
    assert not report.decisions["production_refusal_threshold_changed"]


def test_tracked_bad_case_report_matches_source_reports() -> None:
    generated = build_bad_case_report(PROJECT_ROOT).to_dict()
    tracked = json.loads(
        (PROJECT_ROOT / "evaluation" / "bad_case_report.json").read_text(
            encoding="utf-8"
        )
    )

    assert generated == tracked
