"""Offline refusal-threshold analysis over one completed retrieval run."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def analyze_refusal_thresholds(
    question_results: Sequence[dict[str, Any]],
    *,
    minimum_threshold: float,
    thresholds: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Simulate score thresholds without making additional embedding requests."""

    candidates = (
        tuple(
            round(value / 100, 2)
            for value in range(round(minimum_threshold * 100), 101)
        )
        if thresholds is None
        else tuple(thresholds)
    )
    _validate_thresholds(candidates, minimum_threshold)

    answerable = [
        result for result in question_results if result["expected_behavior"] == "answer"
    ]
    unanswerable = [
        result for result in question_results if result["expected_behavior"] == "refuse"
    ]
    if not answerable or not unanswerable:
        raise ValueError("threshold analysis requires answerable and refusal questions")

    sweep = tuple(
        _evaluate_threshold(answerable, unanswerable, threshold)
        for threshold in candidates
    )
    recommended = max(
        sweep,
        key=lambda row: (
            row["balanced_score"],
            row["unanswerable_rejection_rate"],
            row["evidence_recall"],
            -row["answerable_false_refusal_rate"],
            -row["threshold"],
        ),
    )
    return {
        "method": "offline-score-sweep",
        "minimum_observable_threshold": minimum_threshold,
        "answerable_question_count": len(answerable),
        "unanswerable_question_count": len(unanswerable),
        "recommended_threshold_on_this_dataset": recommended["threshold"],
        "recommended_metrics": recommended,
        "sweep": list(sweep),
    }


def _evaluate_threshold(
    answerable: list[dict[str, Any]],
    unanswerable: list[dict[str, Any]],
    threshold: float,
) -> dict[str, float]:
    per_question_recalls: list[float] = []
    evidence_hits = 0
    retained_answers = 0
    for question in answerable:
        retained_results = [
            result for result in question["results"] if result["score"] >= threshold
        ]
        retained_answers += int(bool(retained_results))
        matched_evidence = {
            number
            for result in retained_results
            for number in result["matched_evidence_numbers"]
        }
        expected_count = len(question["expected_evidence"])
        recall = len(matched_evidence) / expected_count
        per_question_recalls.append(recall)
        evidence_hits += int(bool(matched_evidence))

    rejected_unanswerable = sum(
        not any(result["score"] >= threshold for result in question["results"])
        for question in unanswerable
    )
    evidence_recall = sum(per_question_recalls) / len(per_question_recalls)
    evidence_hit_rate = evidence_hits / len(answerable)
    answerable_retention_rate = retained_answers / len(answerable)
    unanswerable_rejection_rate = rejected_unanswerable / len(unanswerable)
    balanced_score = _harmonic_mean(evidence_recall, unanswerable_rejection_rate)
    return {
        "threshold": round(threshold, 4),
        "evidence_hit_rate": round(evidence_hit_rate, 4),
        "evidence_recall": round(evidence_recall, 4),
        "answerable_retention_rate": round(answerable_retention_rate, 4),
        "answerable_false_refusal_rate": round(1.0 - answerable_retention_rate, 4),
        "unanswerable_rejection_rate": round(unanswerable_rejection_rate, 4),
        "balanced_score": round(balanced_score, 4),
    }


def _harmonic_mean(left: float, right: float) -> float:
    return 0.0 if left + right == 0.0 else 2 * left * right / (left + right)


def _validate_thresholds(
    thresholds: tuple[float, ...],
    minimum_threshold: float,
) -> None:
    if not 0.0 <= minimum_threshold <= 1.0:
        raise ValueError("minimum_threshold must be between 0 and 1")
    if not thresholds:
        raise ValueError("at least one threshold is required")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not minimum_threshold <= value <= 1.0
        for value in thresholds
    ):
        raise ValueError(
            "thresholds must be numbers between the observable floor and 1"
        )
    if tuple(sorted(set(thresholds))) != thresholds:
        raise ValueError("thresholds must be unique and sorted")
