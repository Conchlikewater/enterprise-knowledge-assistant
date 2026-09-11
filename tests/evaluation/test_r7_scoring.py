import json
from types import SimpleNamespace

import pytest

from evaluation.experiments.r7_assets import bind_assertions
from evaluation.experiments.r7_replay import pack_result, replay, write_new
from evaluation.experiments.r7_retrieval import Hit, run_arm
from evaluation.experiments.r7_scoring import score_citations, score_retrieval


def h(cid, doc="d"):
    return Hit(cid, doc, 1, 0.8)


def test_recall_counts_units_but_ndcg_gains_only_once_per_rank():
    units = [{"chunk_ids": ["a"]}, {"chunk_ids": ["a"]}]
    scores = score_retrieval([h("a")], units, {"d"})
    assert scores["evidence_recall_at_5"] == 1
    assert 0 < scores["ndcg_at_5"] < 1
    assert scores["mrr"] == 1


def test_rank_six_not_in_recall5_and_refusal_denominator_not_fabricated():
    hits = [h(str(i)) for i in range(6)]
    scores = score_retrieval(hits, [{"chunk_ids": ["5"]}], {"d"})
    assert scores["evidence_recall_at_5"] == 0
    assert scores["mrr"] == 1 / 6
    assert scores["all_candidate_evidence_coverage"] == 1
    assert score_retrieval([], [], set())["evidence_recall_at_5"] is None
    with pytest.raises(ValueError, match="Duplicate"):
        score_retrieval([h("a"), h("a")], [], {"d"})


def test_paths_require_complete_order_and_scope_is_reported():
    result = score_retrieval(
        [h("a", "hidden")], [], {"d"}, [{"edge_ids": ["ab", "bc"]}], [("bc", "ab")]
    )
    assert result["graph_path_correctness"] == 0
    assert result["scope_violations"] == 1


def test_citation_identity_does_not_imply_gold_support():
    result = score_citations(
        [
            {"chunk_id": "a", "source_id": "d", "page_number": 1},
            {"chunk_id": "b", "source_id": "d", "page_number": 2},
        ],
        [h("a"), h("b")],
        [{"chunk_ids": ["b"]}],
    )
    assert result["identity_source_page_correct"] == 1
    assert result["gold_support_proxy_correct"] == 0
    assert result["evidence_coverage"] == 0


def test_replay_roundtrip_never_exports_query_and_refuses_overwrite(tmp_path):
    result = run_arm("private question", {"d"}, "dense_top5", lambda *_: [h("a")])
    record = pack_result("q1", "dense_top5", result)
    target = tmp_path / "trajectory.json"
    write_new(target, record)
    assert "private question" not in target.read_text()
    loaded = json.loads(target.read_text())
    gold = {"question_id": "q1", "evidence": [{"chunk_ids": ["a"]}]}
    assert replay(loaded, gold, {"d"})["evidence_recall_at_5"] == 1
    with pytest.raises(FileExistsError):
        write_new(target, record)
    with pytest.raises(ValueError, match="identity"):
        replay(loaded, {**gold, "question_id": "wrong"}, {"d"})


def test_binding_uses_source_fields_not_gold_and_rejects_ambiguity():
    edge = {"id": "e", "predicate": "REQUIRES", "source_id": "d", "page_number": 1}
    chunk = SimpleNamespace(
        source_id="d",
        page_number=1,
        kind="prerequisites",
        source_sha256="a",
        chunk_id="c",
    )
    assert bind_assertions({"edges": [edge]}, [chunk])[0]["chunk_id"] == "c"
    with pytest.raises(ValueError, match="unambiguous"):
        bind_assertions({"edges": [edge]}, [chunk, chunk])
