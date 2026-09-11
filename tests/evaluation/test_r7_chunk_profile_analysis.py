import hashlib
import json
from pathlib import Path

import pytest

from evaluation.r7_chunk_profile_analysis import (
    PREFERRED_PROFILE,
    _digest,
    analyze,
)
from evaluation.r7_corpus_contract import ReviewedBlock, review_digest

ROOT = Path(__file__).resolve().parents[2]
R7 = ROOT / "evaluation" / "r7"


def fixture():
    block = ReviewedBlock(
        source_id="source-1",
        source_sha256="a" * 64,
        page_number=1,
        block_id="course-information",
        kind="course_information",
        course_title="高等数学建模（一）",
        course_code="3100311003",
        text="课程名称：高等数学建模（一）。课程编号：3100311003。学分：5。",
    )
    candidate = {
        "question_files_loaded": False,
        "gold_loaded": False,
        "provider_calls": 0,
        "page_decisions": [
            {
                "source_id": block.source_id,
                "source_sha256": block.source_sha256,
                "page_number": 1,
                "decision": "keep",
                "block_ids": [block.block_id],
                "exclusion_reason": None,
            }
        ],
        "block_reviews": [
            {
                "source_id": block.source_id,
                "page_number": 1,
                "block_id": block.block_id,
                "candidate_review_digest": review_digest(block),
            }
        ],
        "blocks": [block.__dict__],
    }
    admission = {
        "status": "approved_for_local_offline_chunking_only",
        "output_sha256": {
            "local_candidate": _digest(candidate),
            "candidate_corpus": _digest(candidate["blocks"]),
        },
        "execution_boundary": {
            "safe_for_local_offline_chunking": True,
            "external_provider_upload_authorized": False,
        },
    }
    development = {
        "questions": [
            {
                "id": "dev-1",
                "answerable": True,
                "expected_evidence": [
                    {
                        "source_id": "source-1",
                        "page_number": 1,
                        "field_key": "credits",
                        "expected_value": "5",
                    }
                ],
            },
            {"id": "dev-2", "answerable": False, "expected_evidence": []},
        ]
    }
    return candidate, admission, development


def test_selects_production_profile_without_loading_formal_questions():
    result = analyze(*fixture())
    assert result["status"] == "chunk_profile_selected"
    assert result["selection_policy"]["selected_profile"] == PREFERRED_PROFILE
    assert result["formal_questions_loaded"] is False
    assert result["provider_calls"] == 0
    chosen = result["profiles"][PREFERRED_PROFILE]
    assert chosen["development"]["mapped_targets"] == 1
    assert chosen["course_identity_rate"] == 1


def test_tampered_candidate_is_rejected_before_chunking():
    candidate, admission, development = fixture()
    candidate["blocks"][0]["text"] += "篡改"
    with pytest.raises(ValueError, match="admitted hashes"):
        analyze(candidate, admission, development)


def test_unanswerable_development_question_cannot_declare_gold():
    candidate, admission, development = fixture()
    development["questions"][1]["expected_evidence"] = [
        {
            "source_id": "source-1",
            "page_number": 1,
            "field_key": "credits",
            "expected_value": "5",
        }
    ]
    with pytest.raises(ValueError, match="Unanswerable"):
        analyze(candidate, admission, development)


def test_report_digest_is_canonical_not_file_format_dependent():
    value = {"b": 1, "a": "课程"}
    assert _digest(value) == _digest(json.loads(json.dumps(value)))


def test_frozen_profile_is_bound_to_current_analysis_implementation():
    freeze = json.loads(
        (R7 / "preparation/r7b_chunk_profile_freeze_20260910.json").read_text(
            encoding="utf-8"
        )
    )
    implementation = ROOT / "evaluation/r7_chunk_profile_analysis.py"
    assert freeze["status"] == "chunk_profile_frozen"
    assert freeze["selection_policy"]["selected_profile"] == PREFERRED_PROFILE
    assert freeze["selection_policy"]["formal_results_used"] is False
    assert freeze["selection_policy"]["provider_calls"] == 0
    assert (
        hashlib.sha256(implementation.read_bytes()).hexdigest()
        == freeze["analysis_implementation_sha256"]
    )
