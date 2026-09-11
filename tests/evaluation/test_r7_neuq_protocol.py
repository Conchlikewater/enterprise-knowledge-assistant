import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
R7 = ROOT / "evaluation" / "r7"


def load(path):
    return json.loads((R7 / path).read_text(encoding="utf-8"))


def file_hash(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def test_new_protocol_binds_all_current_preregistration_assets():
    protocol = load("neuq_2023_protocol.json")
    assert protocol["status"] == "preregistered_frozen"
    for asset in protocol["frozen_assets"].values():
        assert file_hash(asset["path"]) == asset["file_sha256"]
    assert protocol["frozen_assets"]["formal_questions"]["count"] == 100
    assert protocol["chunking"]["expected_chunk_count"] == 1241


def test_three_arms_control_retry_budget_and_share_one_corpus():
    protocol = load("neuq_2023_protocol.json")
    arms = {arm["id"]: arm for arm in protocol["retrieval_arms"]}
    assert set(arms) == {
        "dense_top5",
        "dense_retry_5x2",
        "graph_dense_retry_5x2",
    }
    assert arms["dense_top5"]["final_unique_budget"] == 5
    assert arms["dense_retry_5x2"]["final_unique_budget"] == 10
    assert arms["graph_dense_retry_5x2"]["final_unique_budget"] == 10
    assert protocol["chunking"]["same_immutable_chunks_required_for_all_arms"] is True
    assert protocol["retry_policy"]["decision_input"].startswith("Dense results")


def test_calibration_and_engineering_acceptance_unlock_formal_run():
    protocol = load("neuq_2023_protocol.json")
    retry = protocol["retry_policy"]
    assert retry["semantic_score_threshold"] == 0.53
    assert retry["selection_data"] == "10 development questions only"
    assert retry["formal_100_results_forbidden"] is True
    assert protocol["authorization"]["aggregate_budget_cny"] == 10
    assert protocol["phase_gate"]["r7b_complete"] is True
    assert protocol["phase_gate"]["r7c_graph_code_allowed"] is True
    acceptance = load("preparation/r7c_acceptance_20260910.json")
    assert acceptance["status"] == "engineering_acceptance_passed"
    assert acceptance["formal_questions_executed"] == 0
    assert protocol["phase_gate"]["r7d_formal_results_allowed"] is True


def test_gold_denominators_and_negative_result_boundary_are_explicit():
    protocol = load("neuq_2023_protocol.json")
    historical = load("protocol.json")
    assert (
        protocol["scoring"]["ndcg_at_5"]
        == historical["evidence_scoring"]["evidence_ndcg_at_5"]
    )
    gold = protocol["gold"]
    assert sum(gold["categories"].values()) == gold["questions"] == 100
    assert sum(gold["expected_behavior"].values()) == 100
    assert gold["evidence_units"] == 125
    assert gold["graph_path_questions"] == 63
    assert protocol["promotion_gates"]["all_required"] is True
    assert "negative" in protocol["promotion_gates"]["failure"]
    boundaries = protocol["reporting_boundaries"]
    assert boundaries["do_not_claim_automatic_graph_extraction"] is True
    assert boundaries["do_not_claim_production_graphrag"] is True
