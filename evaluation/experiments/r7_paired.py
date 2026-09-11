"""Strict question-ID pairing and reproducible descriptive bootstrap intervals."""

from math import ceil, isfinite
from random import Random
from statistics import mean


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, ceil(fraction * len(ordered)) - 1)] if ordered else None


def paired_delta(
    baseline, candidate, metric, *, categories=None, resamples=10000, seed=20260908
):
    def index(rows):
        indexed = {row["question_id"]: row for row in rows}
        if len(indexed) != len(rows):
            raise ValueError("Duplicate question ID")
        return indexed

    left, right = index(baseline), index(candidate)
    if left.keys() != right.keys():
        raise ValueError("Paired question sets differ")
    deltas = []
    for qid in sorted(left):
        a, b = left[qid], right[qid]
        if a["category"] != b["category"]:
            raise ValueError("Paired category mismatch")
        if categories is not None and a["category"] not in categories:
            continue
        x, y = a[metric], b[metric]
        if (x is None) != (y is None):
            raise ValueError("Paired metric denominators differ")
        if x is None:
            continue
        if not isfinite(x) or not isfinite(y):
            raise ValueError("Nonfinite metric")
        deltas.append({"question_id": qid, "delta": y - x})
    values = [row["delta"] for row in deltas]
    if resamples < 1:
        raise ValueError("Bootstrap count must be positive")
    rng = Random(seed)
    samples = (
        [mean(rng.choices(values, k=len(values))) for _ in range(resamples)]
        if values
        else []
    )
    return {
        "paired_n": len(values),
        "mean_delta": mean(values) if values else None,
        "wins": sum(x > 0 for x in values),
        "ties": sum(x == 0 for x in values),
        "losses": sum(x < 0 for x in values),
        "per_question": deltas,
        "bootstrap_seed": seed,
        "bootstrap_resamples": resamples,
        "percentile95": [percentile(samples, 0.025), percentile(samples, 0.975)],
        "significance_claim": False,
    }


def confusion(rows):
    counts = {
        f"{expected}_{actual}": 0
        for expected in ("answer", "refuse")
        for actual in ("answer", "refuse")
    }
    for row in rows:
        key = f"{row['expected_behavior']}_{row['behavior']}"
        if key not in counts:
            raise ValueError("Invalid behavior label")
        counts[key] += 1
    return {
        "counts": counts,
        "n": len(rows),
        "accuracy": (counts["answer_answer"] + counts["refuse_refuse"]) / len(rows)
        if rows
        else None,
    }
