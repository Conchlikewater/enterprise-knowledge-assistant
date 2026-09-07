from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from evaluation.r6_routing_evaluation import (
    _load_locked_asset,
    classification_metrics,
    latency_summary,
)


def test_classification_metrics_exposes_confusion_and_macro_scores() -> None:
    metrics = classification_metrics(
        ["retrieve", "retrieve", "direct"],
        ["retrieve", "direct", "direct"],
        ["retrieve", "direct"],
    )

    assert metrics["confusion_matrix"] == {
        "retrieve": {"retrieve": 1, "direct": 1},
        "direct": {"retrieve": 0, "direct": 1},
    }
    assert metrics["accuracy"] == pytest.approx(2 / 3)
    assert metrics["per_class"]["retrieve"] == {
        "precision": 1.0,
        "recall": 0.5,
        "f1": pytest.approx(2 / 3),
        "support": 2,
    }
    assert metrics["macro_f1"] == pytest.approx(2 / 3)


@pytest.mark.parametrize(
    ("expected", "predicted", "labels", "message"),
    [
        (["a"], [], ["a"], "same sample count"),
        (["a"], ["a"], [], "non-empty and unique"),
        (["a"], ["b"], ["a"], "unknown labels"),
    ],
)
def test_classification_metrics_rejects_invalid_inputs(
    expected: list[str],
    predicted: list[str],
    labels: list[str],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        classification_metrics(expected, predicted, labels)


def test_latency_summary_uses_nearest_rank_percentiles() -> None:
    assert latency_summary([])["sample_count"] == 0
    assert latency_summary([4.0, 1.0, 3.0, 2.0]) == {
        "sample_count": 4,
        "mean": 2.5,
        "p50": 2.0,
        "p95": 4.0,
        "max": 4.0,
        "unit": "ms",
    }


def test_locked_asset_loader_rejects_a_changed_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps({"samples": []}), encoding="utf-8")
    expected_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()

    path, payload = _load_locked_asset(tmp_path, "fixture.json", expected_hash)

    assert path == fixture
    assert payload == {"samples": []}
    with pytest.raises(ValueError, match="hash mismatch"):
        _load_locked_asset(tmp_path, "fixture.json", "0" * 64)
