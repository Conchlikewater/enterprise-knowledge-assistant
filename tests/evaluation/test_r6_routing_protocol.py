import hashlib
import json
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load(relative_path: str) -> dict:
    return json.loads((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))


def _sha256(relative_path: str) -> str:
    return hashlib.sha256((PROJECT_ROOT / relative_path).read_bytes()).hexdigest()


def test_r6_protocol_is_frozen_before_implementation_and_blocks_r7() -> None:
    protocol = _load("evaluation/r6_routing_protocol.json")

    assert protocol["status"] == "preregistered_before_implementation"
    assert protocol["authorization"] == {
        "r6_authorized": True,
        "r7_authorized_before_r6_acceptance": False,
        "latest_user_scope_supersedes_the_earlier_r6_r7_deferral": True,
    }
    assert protocol["implementation_at_freeze"] == {
        "routing_controller_implemented": False,
        "retry_controller_implemented": False,
        "evaluation_executed": False,
        "real_provider_called": False,
    }
    boundaries = protocol["execution_boundaries"]
    assert boundaries["real_provider_authorized"] is False
    assert boundaries["paid_calls_allowed"] is False
    assert boundaries["r7_graph_code_allowed"] is False
    assert boundaries["r7_school_corpus_collection_allowed"] is False
    assert boundaries["r7_question_authoring_allowed"] is False


def test_r6_route_dataset_is_balanced_and_hash_locked() -> None:
    protocol = _load("evaluation/r6_routing_protocol.json")
    assets = protocol["frozen_evaluation_assets"]
    dataset_path = assets["route_dataset"]
    dataset = _load(dataset_path)
    samples = dataset["samples"]

    assert dataset["status"] == "frozen_before_implementation"
    assert dataset["r7_reuse_forbidden"] is True
    assert len(samples) == assets["route_sample_count"] == 36
    assert Counter(sample["expected_route"] for sample in samples) == {
        "retrieve": 12,
        "direct_answer": 12,
        "refuse": 12,
    }
    assert len({sample["id"] for sample in samples}) == len(samples)
    assert all(sample["text"].strip() for sample in samples)
    assert _sha256(dataset_path) == assets["route_dataset_sha256"]


def test_r6_retry_dataset_and_budget_are_hash_locked() -> None:
    protocol = _load("evaluation/r6_routing_protocol.json")
    assets = protocol["frozen_evaluation_assets"]
    dataset_path = assets["retry_dataset"]
    dataset = _load(dataset_path)
    retry = protocol["retry_policy"]

    assert dataset["status"] == "frozen_before_implementation"
    assert len(dataset["cases"]) == assets["retry_case_count"] == 12
    assert len({case["id"] for case in dataset["cases"]}) == 12
    assert _sha256(dataset_path) == assets["retry_dataset_sha256"]
    assert retry["max_retrieval_calls"] == 2
    assert retry["per_round_result_limit_max"] == 5
    assert retry["total_raw_result_budget_max"] == 10
    assert retry["document_ids_must_equal_top_level_scope_on_every_call"] is True
    assert retry["retry_on_retrieval_exception"] is False


def test_r6_protocol_prevents_business_fact_direct_answers() -> None:
    protocol = _load("evaluation/r6_routing_protocol.json")
    routes = {route["id"]: route for route in protocol["routes"]}
    constraints = protocol["implementation_constraints"]

    assert set(routes) == {"retrieve", "direct_answer", "refuse"}
    assert routes["direct_answer"]["llm_may_be_called"] is False
    assert routes["refuse"]["llm_may_be_called"] is False
    assert constraints["business_fact_direct_answer_allowed"] is False
    assert constraints["langgraph_allowed"] is False
    assert constraints["memory_allowed"] is False
    assert constraints["multi_agent_allowed"] is False


def test_r6_acceptance_thresholds_keep_safety_and_regression_gates() -> None:
    protocol = _load("evaluation/r6_routing_protocol.json")
    thresholds = protocol["acceptance_thresholds"]
    reporting = protocol["reporting_rules"]

    assert thresholds["routing_accuracy_min"] >= 0.9
    assert thresholds["routing_macro_f1_min"] >= 0.85
    assert thresholds["business_fact_direct_answer_violation_max"] == 0
    assert thresholds["retry_trigger_precision_min"] >= 0.8
    assert thresholds["retry_trigger_recall_min"] >= 0.8
    assert thresholds["retrieval_call_limit_breach_max"] == 0
    assert thresholds["document_scope_violation_max"] == 0
    assert thresholds["legacy_v1_answer_regressions_max"] == 0
    assert reporting["failed_thresholds_block_r7"] is True
    assert reporting["results_must_not_be_described_as_a_general_agent"] is True
