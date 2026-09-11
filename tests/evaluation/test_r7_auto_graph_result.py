import json
from pathlib import Path


def test_auto_graph_summary_never_promotes_format_success_to_semantic_quality():
    path = Path(__file__).parents[2] / "evaluation/r7/results/auto_graph_20260910.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    smoke, final = report["smoke_v1"], report["review_v1_1"]
    assert smoke["sources"] + final["sources"] == 44
    assert smoke["known_directory_applicability_errors"] == 4
    assert final["edges"] == sum(final["edge_types"].values()) == 139
    assert final["nodes"] == 179
    assert report["independent_human_review_coverage"] == 0
    assert report["human_reviewed_precision"] is None
    assert report["exhaustively_annotated_recall"] is None
    assert report["promotion_gate_passed"] is False
    assert report["production_integration"] is False
    assert report["new_retrieval_comparison_run"] is False
