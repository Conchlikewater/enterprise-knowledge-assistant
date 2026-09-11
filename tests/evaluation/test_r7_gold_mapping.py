import hashlib
import json
from pathlib import Path

import pytest

from evaluation.r7_corpus_contract import profile_digest
from evaluation.r7_gold_mapping import FORMAL_PROFILE, _kind, _terms, freeze

ROOT = Path(__file__).resolve().parents[2]
R7 = ROOT / "evaluation" / "r7"


@pytest.mark.parametrize(
    ("field", "kind"),
    [
        ("先修课程", "prerequisites"),
        ("课程学分/课程属性", "course_information"),
        ("课程编号/实验学时", "course_information"),
        ("成绩评定/期末", "assessment"),
        ("表2/知识单元五与六", "teaching_schedule"),
        ("知识单元八/学习目标", "teaching_schedule"),
        ("专业目标1-4", "learning_objectives"),
        ("整体目标", "learning_objectives"),
    ],
)
def test_structural_fields_map_to_reviewed_block_kinds(field, kind):
    assert _kind(field) == kind


def test_unknown_structural_field_fails_instead_of_guessing():
    with pytest.raises(ValueError, match="Unmapped"):
        _kind("教师姓名")


def test_lexical_terms_keep_identifiers_and_chinese_bigrams():
    terms = _terms("课程编号 3100213019 的计算机网络组网技术")
    assert "3100213019" in terms
    assert {"计算", "网络", "组网"} <= terms


def test_freeze_rejects_manual_decisions_for_non_candidates():
    proposal = {
        "candidate_corpus_sha256": "a" * 64,
        "questions": [
            {
                "question_id": "q1",
                "locators": [
                    {
                        "locator_index": 1,
                        "status": "pending_manual_choice",
                        "candidates": [
                            {"chunk_id": "candidate", "content_sha256": "b" * 64}
                        ],
                    }
                ],
            }
        ],
    }
    manual = {
        "candidate_corpus_sha256": "a" * 64,
        "profile_sha256": profile_digest(FORMAL_PROFILE),
        "choices": [{"key": "q1:1", "chunk_id": "not-a-candidate"}],
    }
    admission = {"output_sha256": {"candidate_corpus": "a" * 64}}
    formal = {
        "questions": [
            {
                "id": "q1",
                "gold_path_candidates": [],
            }
        ]
    }
    with pytest.raises(ValueError, match="non-candidate"):
        freeze(proposal, manual, formal, {"edges": []}, {}, admission)


def test_gold_freeze_manifest_binds_inputs_and_keeps_experiment_unrun():
    manifest = json.loads(
        (R7 / "preparation/r7b_gold_freeze_20260910.json").read_text(encoding="utf-8")
    )
    manual_path = R7 / "preparation/r7b_gold_manual_decisions_20260910.json"
    generator_path = ROOT / "evaluation/r7_gold_mapping.py"
    assert manifest["status"] == "chunk_and_graph_gold_frozen"
    assert manifest["summary"]["questions"] == 100
    assert manifest["summary"]["evidence_locators"] == 125
    assert manifest["summary"]["manually_selected_locators"] == 8
    assert manifest["integrity"]["provider_calls"] == 0
    assert manifest["integrity"]["formal_results_used_for_parameter_selection"] is False
    assert (
        hashlib.sha256(manual_path.read_bytes()).hexdigest()
        == manifest["input_file_sha256"]["manual_decisions"]
    )
    assert (
        hashlib.sha256(generator_path.read_bytes()).hexdigest()
        == manifest["reconstruction"]["generator_sha256"]
    )
