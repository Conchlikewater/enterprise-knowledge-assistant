import json
from pathlib import Path

import pytest

from evaluation.experiments.r7_replay import pack_result
from evaluation.experiments.r7_report import ARMS, build_report, judge_promotion
from evaluation.experiments.r7_retrieval import Hit, run_arm


def fixture():
    hits = [Hit("a", "d", 1, 0.8), Hit("b", "d", 2, 0.7)]
    result = run_arm("q", {"d"}, "dense_top5", lambda *_: hits)
    records = [pack_result("q", arm, result) for arm in ARMS]
    gold = [
        {
            "question_id": "q",
            "category": "ordinary_fact",
            "expected_behavior": "refuse",
            "evidence": [{"chunk_ids": ["a"]}],
            "gold_graph_paths": [],
        }
    ]
    return records, gold, {"q": {"d"}}


def test_report_does_not_use_expected_refusal_to_control_decision():
    report = build_report(*fixture(), resamples=10)
    assert report["question_count"] == 1
    assert len(report["paired"]) == 3
    for arm in report["arms"].values():
        assert arm["answer_refuse"]["counts"]["refuse_answer"] == 1
        assert arm["rows"][0]["citations"]["gold_support_proxy_correct"] == 1


def test_missing_arm_cannot_silently_shrink_denominator():
    records, gold, scopes = fixture()
    with pytest.raises(ValueError, match="Incomplete"):
        build_report(records[:-1], gold, scopes, resamples=10)


def test_third_call_rejected_in_replay_report():
    records, gold, scopes = fixture()
    records[0]["retrieval_calls"] = 3
    with pytest.raises(ValueError, match="budget"):
        build_report(records, gold, scopes, resamples=10)


def test_missing_multihop_and_path_denominators_cannot_pass_promotion():
    protocol = json.loads(
        (Path(__file__).parents[2] / "evaluation/r7/neuq_2023_protocol.json").read_text(
            encoding="utf-8"
        )
    )
    result = judge_promotion(
        build_report(*fixture(), resamples=10), protocol["promotion_gates"]
    )
    assert len(result["checks"]) == 11
    assert result["checks"]["graph_path"] is False
    assert result["checks"]["multi_evidence"] is False
    assert result["all_passed"] is False
    assert result["production_integration_authorized"] is False
