import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_tracked_experiment_report_contains_isolated_profiles() -> None:
    report = json.loads(
        (PROJECT_ROOT / "evaluation" / "experiment_report.json").read_text(
            encoding="utf-8"
        )
    )

    assert report["all_runs_completed"]
    assert report["profile_count"] == 5
    assert report["question_count"] == 50
    profiles = report["profiles"]
    assert [profile["name"] for profile in profiles] == [
        "baseline-220-30-k5",
        "small-160-30-k5",
        "large-320-50-k5",
        "baseline-220-30-k3",
        "baseline-220-30-k10",
    ]
    assert all(profile["bad_case_ids"] for profile in profiles)
    assert all(len(profile["clarification_cases"]) == 2 for profile in profiles)
    assert all("delta_vs_baseline" in profile for profile in profiles)

    latest_report = json.loads(
        (PROJECT_ROOT / "evaluation" / "latest_report.json").read_text(encoding="utf-8")
    )
    baseline = profiles[0]
    assert baseline["evidence_recall_at_k"] == latest_report["evidence_recall_at_k"]
    assert baseline["bad_case_count"] == latest_report["bad_case_count"]
