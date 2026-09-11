import json
from pathlib import Path
from statistics import mean

import pytest

RESULTS = Path(__file__).parents[2] / "evaluation/r7/results"


def test_published_formal_rows_match_summary_without_dropping_negative_cases():
    summary = json.loads((RESULTS / "neuq_202309_100q_20260910.json").read_text())
    table = json.loads((RESULTS / "neuq_202309_100q_rows_20260910.json").read_text())
    rows = [dict(zip(table["columns"], row, strict=True)) for row in table["rows"]]
    assert len(rows) == 300
    assert len({(r["arm"], r["question_id"]) for r in rows}) == 300
    for arm, expected in summary["results"]["arms"].items():
        group = [r for r in rows if r["arm"] == arm]
        assert len(group) == 100
        values = [r["recall_at_5"] for r in group if r["recall_at_5"] is not None]
        assert len(values) == 89
        assert mean(values) == pytest.approx(
            expected["metrics"]["evidence_recall_at_5"]["mean"]
        )
        assert sum(r["expected_behavior"] == "refuse" for r in group) == 11
    graph = [r for r in rows if r["arm"] == "graph_dense_retry_5x2"]
    assert all(r["behavior"] == "answer" for r in graph)
    assert summary["results"]["promotion"]["all_passed"] is False
    assert summary["results"]["promotion"]["checks"]["graph_path"] is False
    assert summary["execution"]["completed_arm_runs"] == 300
