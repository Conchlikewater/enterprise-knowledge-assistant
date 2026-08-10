"""Dependency-free information-retrieval metrics for offline evaluation."""

from __future__ import annotations

from collections.abc import Callable, Collection, Hashable, Sequence


def hit_rate_at_k[RetrievedItem, RelevantItem: Hashable](
    rankings: Sequence[Sequence[RetrievedItem]],
    relevant_items: Sequence[Collection[RelevantItem]],
    k: int,
    *,
    matcher: Callable[[RetrievedItem, RelevantItem], bool] | None = None,
) -> float:
    """Return the fraction of queries with at least one relevant result in Top-K."""

    pairs = _validated_pairs(rankings, relevant_items)
    _validate_k(k)
    hits = sum(
        any(
            _matches(result, expected, matcher)
            for result in ranking[:k]
            for expected in relevant
        )
        for ranking, relevant in pairs
    )
    return hits / len(pairs) if pairs else 0.0


def recall_at_k[RetrievedItem, RelevantItem: Hashable](
    rankings: Sequence[Sequence[RetrievedItem]],
    relevant_items: Sequence[Collection[RelevantItem]],
    k: int,
    *,
    matcher: Callable[[RetrievedItem, RelevantItem], bool] | None = None,
) -> float:
    """Return mean per-query recall across the supplied rankings."""

    pairs = _validated_pairs(rankings, relevant_items)
    _validate_k(k)
    recalls = [
        sum(
            any(_matches(result, expected, matcher) for result in ranking[:k])
            for expected in set(relevant)
        )
        / len(set(relevant))
        for ranking, relevant in pairs
    ]
    return sum(recalls) / len(recalls) if recalls else 0.0


def mean_reciprocal_rank[RetrievedItem, RelevantItem: Hashable](
    rankings: Sequence[Sequence[RetrievedItem]],
    relevant_items: Sequence[Collection[RelevantItem]],
    *,
    matcher: Callable[[RetrievedItem, RelevantItem], bool] | None = None,
) -> float:
    """Return the mean reciprocal rank of the first relevant result per query."""

    pairs = _validated_pairs(rankings, relevant_items)
    reciprocal_ranks: list[float] = []
    for ranking, relevant in pairs:
        relevant_set = set(relevant)
        first_rank = next(
            (
                rank
                for rank, item in enumerate(ranking, start=1)
                if any(_matches(item, expected, matcher) for expected in relevant_set)
            ),
            None,
        )
        reciprocal_ranks.append(0.0 if first_rank is None else 1.0 / first_rank)
    return sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0.0


def _validated_pairs[RetrievedItem, RelevantItem: Hashable](
    rankings: Sequence[Sequence[RetrievedItem]],
    relevant_items: Sequence[Collection[RelevantItem]],
) -> list[tuple[Sequence[RetrievedItem], Collection[RelevantItem]]]:
    if len(rankings) != len(relevant_items):
        raise ValueError(
            "rankings and relevant_items must contain the same query count"
        )
    pairs = list(zip(rankings, relevant_items, strict=True))
    if any(not relevant for _, relevant in pairs):
        raise ValueError(
            "retrieval metrics require at least one relevant item per query"
        )
    return pairs


def _matches[RetrievedItem, RelevantItem](
    result: RetrievedItem,
    expected: RelevantItem,
    matcher: Callable[[RetrievedItem, RelevantItem], bool] | None,
) -> bool:
    return result == expected if matcher is None else matcher(result, expected)


def _validate_k(k: int) -> None:
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("k must be a positive integer")
