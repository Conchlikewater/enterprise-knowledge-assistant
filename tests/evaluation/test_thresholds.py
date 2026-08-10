import pytest

from evaluation.thresholds import analyze_refusal_thresholds


def _question(
    behavior: str,
    scores_and_matches: list[tuple[float, list[int]]],
) -> dict[str, object]:
    return {
        "expected_behavior": behavior,
        "expected_evidence": ([{"evidence_number": 1}] if behavior == "answer" else []),
        "results": [
            {"score": score, "matched_evidence_numbers": matches}
            for score, matches in scores_and_matches
        ],
    }


def test_threshold_sweep_balances_evidence_and_refusal() -> None:
    questions = [
        _question("answer", [(0.9, [1])]),
        _question("answer", [(0.8, [1])]),
        _question("refuse", [(0.7, [])]),
        _question("refuse", []),
    ]

    analysis = analyze_refusal_thresholds(
        questions,
        minimum_threshold=0.25,
        thresholds=(0.25, 0.71, 0.91),
    )

    assert analysis["recommended_threshold_on_this_dataset"] == 0.71
    assert analysis["recommended_metrics"] == {
        "threshold": 0.71,
        "evidence_hit_rate": 1.0,
        "evidence_recall": 1.0,
        "answerable_retention_rate": 1.0,
        "answerable_false_refusal_rate": 0.0,
        "unanswerable_rejection_rate": 1.0,
        "balanced_score": 1.0,
    }


@pytest.mark.parametrize(
    "thresholds",
    [(), (0.2,), (0.5, 0.4), (0.5, 0.5), (True,)],
)
def test_threshold_sweep_rejects_invalid_candidates(
    thresholds: tuple[float, ...],
) -> None:
    questions = [
        _question("answer", [(0.9, [1])]),
        _question("refuse", []),
    ]

    with pytest.raises(ValueError):
        analyze_refusal_thresholds(
            questions,
            minimum_threshold=0.25,
            thresholds=thresholds,
        )


def test_threshold_sweep_requires_both_question_groups() -> None:
    with pytest.raises(ValueError, match="answerable and refusal"):
        analyze_refusal_thresholds(
            [_question("answer", [(0.9, [1])])],
            minimum_threshold=0.25,
        )
