import hashlib
import json
from pathlib import Path

import pytest

from evaluation.r7_safe_corpus import (
    _fact_blocks,
    _sanitize_line,
    _sensitive_terms,
    manifest,
)

ROOT = Path(__file__).resolve().parents[2]
R7 = ROOT / "evaluation" / "r7"


def load(name):
    return json.loads((R7 / name).read_text(encoding="utf-8"))


def test_reviewed_course_facts_cover_selected_sources_and_source_bytes():
    facts = load("neuq_2023_course_facts.json")
    selected = []
    for index, name in enumerate(
        ("neuq_2023_source_lock.json", "neuq_2023_ce_source_lock.json")
    ):
        lock = load(name)
        selected.extend(
            d
            for d in lock["documents"]
            if index == 0 or d["selected_for_candidate_work"]
        )
    assert len(facts["documents"]) == facts["document_count"] == len(selected) == 44
    by_id = {f["source_id"]: f for f in facts["documents"]}
    assert by_id.keys() == {s["id"] for s in selected}
    for source in selected:
        fact = by_id[source["id"]]
        assert fact["source_sha256"] == source["sha256"]
        assert fact["page_number"] == 1
        assert fact["source_page_visually_reviewed"] is True
        assert fact["course_title"] and fact["course_code"]
        assert fact["credits"] and fact["semester"]
        assert fact["result_type"] in {"百分制", "五级制"}
        assert fact["prerequisite_declaration"] in {
            "explicit_none",
            "blank_not_explicit_none",
            "stated_list_or_name",
        }
        if fact["prerequisite_declaration"] == "blank_not_explicit_none":
            assert fact["prerequisite_text"] is None
        else:
            assert fact["prerequisite_text"]


def test_course_facts_are_structural_and_do_not_contain_personnel_or_resources():
    text = json.dumps(
        load("neuq_2023_course_facts.json")["documents"], ensure_ascii=False
    ).casefold()
    for forbidden in (
        "任课教师",
        "课程协调人",
        "课程负责人",
        "审核人",
        "批准人",
        "taught by",
        "textbook",
        "http://",
        "https://",
    ):
        assert forbidden not in text


def fact(declaration="explicit_none", prerequisite="无"):
    return {
        "source_id": "s",
        "source_sha256": "a" * 64,
        "course_title": "示例课程",
        "course_code": "C1",
        "credits": "3",
        "semester": "2",
        "total_hours": "48",
        "lecture_hours": "40",
        "lab_hours": "8",
        "course_attribute": "必修",
        "course_mode": None,
        "result_type": "百分制",
        "catalogue_memberships": ["CST"],
        "reviewed_applicable_programs": [],
        "prerequisite_declaration": declaration,
        "prerequisite_text": prerequisite,
    }


def test_page_one_facts_preserve_blank_vs_explicit_none_without_raw_table():
    explicit = _fact_blocks(fact())[1]
    blank = _fact_blocks(fact("blank_not_explicit_none", None))[1]
    stated = _fact_blocks(fact("stated_list_or_name", "课程A；课程B"))[1]
    assert explicit.text == "先修课程：原表明确写无。"
    assert "未填写" in blank.text and "明确无" in blank.text
    assert stated.text == "先修课程：课程A；课程B"
    assert all(
        b.page_number == 1 and b.course_title == "示例课程"
        for b in (explicit, blank, stated)
    )


def test_personnel_row_keeps_only_safe_left_cell_and_never_echoes_name():
    text, removed = _sanitize_line("考核环节：期末    环节负责人：PRIVATE_NAME", ())
    assert removed is True and text == "考核环节：期末"
    assert "PRIVATE_NAME" not in text
    for value in (
        "任课教师 PRIVATE_NAME",
        "Taught by PRIVATE_NAME",
        "普通正文 PRIVATE_NAME",
    ):
        result, _ = _sanitize_line(value, ("private_name",))
        assert result == ""


def test_personnel_lexicon_does_not_turn_assessment_labels_into_names():
    class Page:
        def extract_text(self, **_kwargs):
            return "任课教师：PRIVATE_NAME  平时 期中 期末 实验 考核环节"

    class Reader:
        def __init__(self):
            self.pages = [Page()]

    terms = _sensitive_terms([Reader()])
    assert {"private", "name"} <= set(terms)
    assert not {"平时", "期中", "期末", "实验", "考核环节"} & set(terms)


def test_urls_and_email_are_removed_without_changing_other_line_content():
    text, _ = _sanitize_line(
        "教学资源 https://example.invalid/path 联系 test@example.invalid 后续内容", ()
    )
    assert "教学资源" in text and "后续内容" in text
    assert "http" not in text and "@" not in text


def test_manifest_never_contains_local_candidate_text():
    candidate = {
        "schema_version": "test",
        "summary": {"blocks": 1},
        "blocks": [{"text": "PRIVATE_LOCAL_TEXT"}],
    }
    result = manifest(candidate)
    serialized = json.dumps(result)
    assert "blocks" not in result and "PRIVATE_LOCAL_TEXT" not in serialized
    assert (
        result["local_candidate_sha256"]
        == hashlib.sha256(
            json.dumps(
                candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
    )


def test_invalid_prerequisite_declaration_is_not_silently_rendered():
    with pytest.raises(ValueError, match="Invalid prerequisite"):
        _fact_blocks({**fact("unknown", None), "prerequisite_text": None})


def test_local_corpus_admission_is_hash_bound_and_does_not_overclaim_privacy():
    admission = load("preparation/r7b_safe_corpus_admission_20260910.json")
    assert admission["status"] == "approved_for_local_offline_chunking_only"
    inputs = admission["input_sha256"]
    tracked_inputs = {
        "cst_source_lock": "neuq_2023_source_lock.json",
        "ce_source_lock": "neuq_2023_ce_source_lock.json",
        "course_facts": "neuq_2023_course_facts.json",
        "safe_corpus_implementation": "../r7_safe_corpus.py",
        "formal_questions_coverage_check_only": "neuq_2023_questions_draft.json",
        "development_questions_coverage_check_only": (
            "neuq_2023_development_questions_draft.json"
        ),
    }
    for key, relative_path in tracked_inputs.items():
        path = (R7 / relative_path).resolve()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == inputs[key]
    assert admission["coverage_check"]["used_for_parameter_selection"] is False
    boundary = admission["execution_boundary"]
    assert boundary["safe_for_local_offline_chunking"] is True
    assert boundary["external_provider_upload_authorized"] is False
    assert boundary["privacy_completeness_claimed"] is False
    assert boundary["provider_calls"] == 0
