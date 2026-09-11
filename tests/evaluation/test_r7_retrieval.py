import pytest

from evaluation.experiments.r7_retrieval import (
    CachedDense,
    Hit,
    PropertyGraph,
    fuse,
    run_arm,
)


def test_cached_dense_scopes_before_topk_and_never_calls_provider():
    dense = CachedDense(
        [hit("outside", doc="hidden"), hit("inside")],
        [[1.0, 0.0], [0.0, 1.0]],
        {"query": [1.0, 0.0]},
    )
    assert [h.chunk_id for h in dense("query", {"d"})] == ["inside"]
    with pytest.raises(ValueError, match="absent"):
        dense("missing", {"d"})


def test_invalid_cached_vectors_rejected():
    with pytest.raises(ValueError, match="vector"):
        CachedDense([hit("x")], [[float("nan")]], {"q": [1.0]})


def hit(cid, score=0.8, doc="d"):
    return Hit(cid, doc, 1, score)


def graph():
    nodes = [{"key": key, "course_name": key} for key in ("Alpha", "Beta", "Gamma")]
    edges = [
        {
            "id": "ab",
            "subject": "Alpha",
            "object": "Beta",
            "predicate": "REQUIRES",
            "source_id": "d",
            "page_number": 1,
        },
        {
            "id": "bc",
            "subject": "Beta",
            "object": "Gamma",
            "predicate": "REQUIRES",
            "source_id": "hidden",
            "page_number": 1,
        },
    ]
    bindings = [
        {
            "assertion_id": e["id"],
            "chunk_id": e["id"],
            "source_id": e["source_id"],
            "page_number": 1,
        }
        for e in edges
    ]
    return PropertyGraph(
        nodes, edges, bindings, {"ab": hit("ab"), "bc": hit("bc", doc="hidden")}
    )


def test_graph_cannot_traverse_hidden_assertion():
    results = graph().search("Alpha prerequisite", frozenset({"d"}))
    assert [h.chunk_id for h in results] == ["ab"]
    assert results[0].path == ("ab",)
    assert graph().search("Alpha prerequisite", frozenset()) == []


def test_fusion_prefers_shared_hit_and_preserves_path():
    shared = Hit("b", "d", 1, 0, ("ab",))
    results = fuse([hit("a"), hit("b", 0.7)], [shared])
    assert results[0].chunk_id == "b"
    assert results[0].path == ("ab",)


@pytest.mark.parametrize("arm", ["dense_retry_5x2", "graph_dense_retry_5x2"])
def test_retry_uses_dense_not_graph_and_never_calls_third_time(arm):
    calls = []

    def search(query, allowed):
        calls.append((query, allowed))
        return [hit(str(len(calls)))]

    result = run_arm("请问 Alpha 需要先修哪些课程？", {"d"}, arm, search, graph())
    assert len(calls) == 2
    assert calls[0][0] != calls[1][0]
    assert calls[0][1] == calls[1][1] == frozenset({"d"})
    assert result["stop_reason"] == "round_limit"
    assert all(len(row["selected_chunk_ids"]) <= 5 for row in result["trace"])
    assert result["unique_candidates"] <= 10


def test_sufficient_dense_and_single_round_do_not_rewrite():
    for arm in ("dense_top5", "dense_retry_5x2"):
        result = run_arm(
            "请问 Alpha 是什么？", {"d"}, arm, lambda *_: [hit("a"), hit("b")]
        )
        assert result["retrieval_calls"] == 1


def test_scope_violation_and_provider_exception_fail_without_retry():
    with pytest.raises(ValueError, match="scope"):
        run_arm("question", {"d"}, "dense_top5", lambda *_: [hit("x", doc="hidden")])
    calls = []

    def broken(*_):
        calls.append(1)
        raise RuntimeError("offline injected failure")

    with pytest.raises(RuntimeError):
        run_arm("请问 Alpha 是什么？", {"d"}, "dense_retry_5x2", broken)
    assert calls == [1]


def test_duplicate_dense_hits_cannot_fake_sufficiency():
    result = run_arm("fixed", {"d"}, "dense_retry_5x2", lambda *_: [hit("a"), hit("a")])
    assert result["trace"][0]["dense_should_retry"] is True
    assert result["stop_reason"] == "no_distinct_rewrite"


def test_provenance_mismatch_rejected():
    with pytest.raises(ValueError, match="provenance"):
        PropertyGraph(
            [{"key": "a"}, {"key": "b"}],
            [
                {
                    "id": "e",
                    "subject": "a",
                    "object": "b",
                    "predicate": "REQUIRES",
                    "source_id": "d",
                    "page_number": 1,
                }
            ],
            [
                {
                    "assertion_id": "e",
                    "source_id": "d",
                    "page_number": 1,
                    "chunk_id": "x",
                }
            ],
            {"x": hit("x", doc="wrong")},
        )
