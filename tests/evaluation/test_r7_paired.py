import pytest

from evaluation.experiments.r7_decision import decide
from evaluation.experiments.r7_paired import confusion, paired_delta
from evaluation.experiments.r7_retrieval import Hit


def row(qid, value, category="ordinary_fact"):
    return {"question_id": qid, "category": category, "metric": value}


def test_pairing_by_id_not_input_order_and_bootstrap_reproducible():
    left = [row("a", 0), row("b", 1)]
    right = [row("b", 0), row("a", 1)]
    result = paired_delta(left, right, "metric", resamples=100)
    assert result["mean_delta"] == 0
    assert (result["wins"], result["losses"]) == (1, 1)
    assert result == paired_delta(left, right, "metric", resamples=100)


@pytest.mark.parametrize(
    "right",
    [
        [row("b", 1)],
        [row("a", None)],
        [row("a", 1, "multi_hop")],
        [row("a", 1), row("a", 1)],
    ],
)
def test_pair_mismatch_fails_instead_of_dropping_questions(right):
    with pytest.raises(ValueError):
        paired_delta([row("a", 0)], right, "metric")


def test_null_denominator_is_not_perfect_score():
    result = paired_delta([row("a", None)], [row("a", None)], "metric")
    assert result["paired_n"] == 0
    assert result["mean_delta"] is None


def test_decision_has_no_gold_and_does_not_compare_rrf_with_cosine():
    a, b = Hit("a", "d", 1, 0.01), Hit("b", "d", 2, 0.01)
    assert decide([a, a], {"d"})["behavior"] == "refuse"
    result = decide([a, b], {"d"})
    assert result["behavior"] == "answer"
    assert len(result["citations"]) == 2
    with pytest.raises(ValueError):
        decide([a], {"other"})


def test_confusion_counts_false_answers_explicitly():
    result = confusion([{"expected_behavior": "refuse", "behavior": "answer"}])
    assert result["counts"]["refuse_answer"] == 1
    assert result["accuracy"] == 0
