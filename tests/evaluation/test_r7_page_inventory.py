import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from evaluation.r7_corpus_contract import (
    ChunkProfile,
    PageDecision,
    ReviewedBlock,
    SourceSnapshot,
    build_complete_corpus,
    review_digest,
)
from evaluation.r7_page_inventory import inventory_sources, summarize_page


def test_inventory_only_exports_hashes_counts_and_fixed_tags():
    text = "课程信息\n任课教师 PRIVATE_NAME_123\n先修课程：私人文本"
    result = summarize_page(text, 1)
    output = json.dumps(result, ensure_ascii=False)
    assert "PRIVATE_NAME_123" not in output and "私人文本" not in output
    assert result["extracted_text_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert result["review_status"] == "pending" and result["safe_blocks"] == []
    assert "personnel" in result["detected_markers"]
    assert summarize_page("无标签的测试名字", 2)["review_status"] == "pending"


def setup_corpus():
    block = ReviewedBlock(
        "s", "a" * 64, 1, "b", "assessment", "示例", "C1", "实验30%。"
    )
    decisions = [
        PageDecision("s", "a" * 64, 1, "keep", ("b",)),
        PageDecision("s", "a" * 64, 2, "exclude", (), "administrative_only"),
    ]
    return block, decisions


def build(decisions, block=None):
    block = block or setup_corpus()[0]
    return build_complete_corpus(
        [block],
        {"s": SourceSnapshot("a" * 64, 2)},
        {("s", 1, "b"): review_digest(block)},
        ChunkProfile(100, 10, False),
        decisions,
    )


def test_complete_page_inventory_can_keep_structural_page_and_exclude_admin():
    _, decisions = setup_corpus()
    assert len(build(decisions)) == 1


@pytest.mark.parametrize(
    "fault", ["missing", "duplicate", "pending", "hash", "reason", "block", "scope"]
)
def test_incomplete_or_stale_page_decisions_block_corpus(fault):
    _, decisions = setup_corpus()
    if fault == "missing":
        decisions.pop()
    elif fault == "duplicate":
        decisions.append(decisions[0])
    elif fault == "pending":
        decisions[1] = replace(decisions[1], decision="pending")
    elif fault == "hash":
        decisions[1] = replace(decisions[1], source_sha256="b" * 64)
    elif fault == "reason":
        decisions[1] = replace(decisions[1], exclusion_reason="not_in_gold")
    elif fault == "block":
        decisions[0] = replace(decisions[0], block_ids=("invented",))
    else:
        decisions[1] = replace(decisions[1], source_id="other")
    with pytest.raises(ValueError):
        build(decisions)


def test_inventory_checks_all_hashes_before_parsing(tmp_path, monkeypatch):
    root, raw = tmp_path / "meta", tmp_path / "raw"
    root.mkdir()
    raw.mkdir()
    (raw / "source.pdf").write_bytes(b"fake")
    (root / "neuq_2023_source_lock.json").write_text(
        json.dumps({"documents": [{"id": "source", "sha256": "0" * 64, "pages": 1}]})
    )
    (root / "neuq_2023_ce_source_lock.json").write_text('{"documents": []}')
    monkeypatch.setattr(
        "evaluation.r7_page_inventory.PdfReader",
        lambda _: pytest.fail("must not parse"),
    )
    with pytest.raises(ValueError, match="hash mismatched"):
        inventory_sources(root, raw)


def test_actual_inventory_covers_all_selected_pages_without_claiming_clearance():
    root = Path(__file__).resolve().parents[2]
    r7 = root / "evaluation" / "r7"
    report = json.loads(
        (r7 / "preparation/r7b_page_inventory_20260910.json").read_text(
            encoding="utf-8"
        )
    )
    sources = {}
    for index, name in enumerate(report["source_lock_hashes"]):
        data = (r7 / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == report["source_lock_hashes"][name]
        sources.update(
            {
                d["id"]: d
                for d in json.loads(data)["documents"]
                if index == 0 or d["selected_for_candidate_work"]
            }
        )
    assert len(report["documents"]) == len(sources) == 44
    count = 0
    for document in report["documents"]:
        source = sources[document["source_id"]]
        assert document["source_sha256"] == source["sha256"]
        assert [p["page_number"] for p in document["pages"]] == list(
            range(1, source["pages"] + 1)
        )
        for page in document["pages"]:
            assert page["review_status"] == "pending" and page["safe_blocks"] == []
            count += 1
    assert count == report["summary"]["pages"] == 605
    assert report["summary"]["privacy_approved_pages"] == 0
    assert report["raw_text_exported"] is report["question_files_loaded"] is False
