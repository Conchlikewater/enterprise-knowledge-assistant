import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = PROJECT_ROOT / "evaluation" / "agentic_retrieval_protocol.json"


def _load_protocol() -> dict[str, object]:
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def test_r5_protocol_is_design_only_and_not_an_agent_result() -> None:
    protocol = _load_protocol()

    assert protocol["status"] == "preregistered_protocol_only"
    assert protocol["agent_implemented"] is False
    assert protocol["experiment_executed"] is False
    assert protocol["production_api_integrated"] is False

    boundaries = protocol["execution_boundaries"]
    assert boundaries["r5_ci_mode"] == "protocol_validation_only"
    assert boundaries["real_provider_authorized"] is False
    assert boundaries["forbidden_production_code_root"] == "app"


def test_r5_protocol_freezes_the_three_budget_control_arms() -> None:
    protocol = _load_protocol()
    arms = {arm["id"]: arm for arm in protocol["comparison_arms"]}

    assert set(arms) == {"dense_top_5", "dense_top_10", "agentic_5x2"}
    assert (
        arms["dense_top_5"]["max_rounds"],
        arms["dense_top_5"]["per_round_result_limit"],
        arms["dense_top_5"]["total_return_budget"],
    ) == (1, 5, 5)
    assert (
        arms["dense_top_10"]["max_rounds"],
        arms["dense_top_10"]["per_round_result_limit"],
        arms["dense_top_10"]["total_return_budget"],
    ) == (1, 10, 10)
    assert (
        arms["agentic_5x2"]["max_rounds"],
        arms["agentic_5x2"]["per_round_result_limit"],
        arms["agentic_5x2"]["max_retrieval_calls"],
        arms["agentic_5x2"]["total_return_budget"],
    ) == (2, 5, 2, 10)


def test_r5_protocol_covers_replay_failures_and_adversarial_cases() -> None:
    protocol = _load_protocol()

    assert {
        "round_queries",
        "ranked_retrieval_results",
        "second_round_decision",
        "stop_reason",
        "failures",
        "tokens_cost_and_latency",
    } <= set(protocol["required_trajectory_sections"])
    assert {
        "WRONG_TOOL_SELECTION",
        "PARAMETER_EXTRACTION_ERROR",
        "LOOP_LIMIT_BREACH",
        "PREMATURE_TERMINATION",
        "UNSUPPORTED_SUMMARY",
    } <= set(protocol["failure_taxonomy"])
    assert set(protocol["adversarial_cases"]) == {
        "EMPTY_TOOL_RESULT",
        "CONTRADICTORY_EVIDENCE",
        "TOOL_TIMEOUT",
        "INVALID_TOOL_OUTPUT",
    }
    assert {
        "round_2_jaccard_similarity",
        "round_2_replacement_ratio",
        "round_2_new_gold_evidence",
    } <= set(protocol["required_metrics"])


def test_r5_assets_are_not_claimed_as_agent_annotations() -> None:
    protocol = _load_protocol()
    questions = json.loads(
        (PROJECT_ROOT / "evaluation" / "questions.json").read_text(encoding="utf-8")
    )["questions"]
    documents = json.loads(
        (PROJECT_ROOT / "evaluation" / "corpus_sources.json").read_text(
            encoding="utf-8"
        )
    )["documents"]
    assets = protocol["current_assets"]

    assert assets["corpus_document_count"] == len(documents) == 10
    assert assets["rag_question_count"] == len(questions) == 50
    assert assets["agent_annotation_status"] == "not_created"
    assert assets["reuse_rule"] == "candidate_source_only"


def test_public_docs_separate_r5_protocol_from_r6_bounded_routing() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    protocol_doc = (
        PROJECT_ROOT / "docs" / "r5_agentic_retrieval_evaluation_protocol.md"
    ).read_text(encoding="utf-8")

    assert "R5 Agentic Retrieval 评测协议（无实现、无结果）" in readme
    assert "R6 受限路由控制器（已实现并完成离线边界评测）" in readme
    assert "它不是通用" in readme
    assert "R7人工图对照与自动构图实验已运行，均未获准接入生产" in readme
    assert "原始PDF全自动GraphRAG" in readme
    assert "未实现、未运行 Agent，也没有实验结果" in protocol_doc
    assert "不能表述为“实现了 Agent”" in protocol_doc
