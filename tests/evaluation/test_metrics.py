import pytest

from evaluation.metrics import hit_rate_at_k, mean_reciprocal_rank, recall_at_k


def test_retrieval_metrics_measure_different_ranking_properties() -> None:
    rankings = [
        ["evidence-a", "noise", "evidence-b"],
        ["noise", "evidence-c"],
        ["noise-only"],
    ]
    relevant_items = [
        {"evidence-a", "evidence-b"},
        {"evidence-c"},
        {"evidence-d"},
    ]

    assert hit_rate_at_k(rankings, relevant_items, k=2) == pytest.approx(2 / 3)
    assert recall_at_k(rankings, relevant_items, k=2) == pytest.approx(0.5)
    assert mean_reciprocal_rank(rankings, relevant_items) == pytest.approx(0.5)


def test_recall_counts_duplicate_results_only_once() -> None:
    rankings = [["evidence-a", "evidence-a", "evidence-b"]]
    relevant_items = [{"evidence-a", "evidence-b"}]

    assert recall_at_k(rankings, relevant_items, k=2) == 0.5
    assert recall_at_k(rankings, relevant_items, k=3) == 1.0


def test_custom_matcher_can_find_multiple_evidence_items_in_one_result() -> None:
    rankings = [["Policy alpha applies. Policy beta applies."]]
    relevant_items = [{"Policy alpha applies.", "Policy beta applies."}]

    def contains_evidence(result: str, evidence: str) -> bool:
        return evidence in result

    assert (
        hit_rate_at_k(
            rankings,
            relevant_items,
            k=1,
            matcher=contains_evidence,
        )
        == 1.0
    )
    assert (
        recall_at_k(
            rankings,
            relevant_items,
            k=1,
            matcher=contains_evidence,
        )
        == 1.0
    )
    assert (
        mean_reciprocal_rank(
            rankings,
            relevant_items,
            matcher=contains_evidence,
        )
        == 1.0
    )


def test_empty_query_collection_returns_zero() -> None:
    assert hit_rate_at_k([], [], k=5) == 0.0
    assert recall_at_k([], [], k=5) == 0.0
    assert mean_reciprocal_rank([], []) == 0.0


@pytest.mark.parametrize("invalid_k", [0, -1, 1.5, True])
def test_top_k_metrics_reject_invalid_k(invalid_k: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        hit_rate_at_k([["evidence"]], [{"evidence"}], k=invalid_k)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive integer"):
        recall_at_k([["evidence"]], [{"evidence"}], k=invalid_k)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("rankings", "relevant_items", "message"),
    [
        ([[]], [], "same query count"),
        ([[]], [set()], "at least one relevant item"),
    ],
)
def test_metrics_reject_malformed_ground_truth(
    rankings: list[list[str]],
    relevant_items: list[set[str]],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        mean_reciprocal_rank(rankings, relevant_items)
