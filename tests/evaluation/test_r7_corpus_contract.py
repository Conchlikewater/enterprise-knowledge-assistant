"""Synthetic input only: no PDF, provider, repository or production data writes."""

from dataclasses import replace

import pytest

from evaluation.r7_corpus_contract import (
    ChunkProfile,
    ReviewedBlock,
    SourceSnapshot,
    assert_same_corpus,
    build_reviewed_chunks,
    review_digest,
)


def fixture_blocks():
    return [
        ReviewedBlock(
            source_id="sample-course",
            source_sha256="a" * 64,
            page_number=page,
            block_id=f"unit-{page}",
            kind="prerequisites" if page == 1 else "assessment",
            course_title="示例课程",
            course_code="C101",
            text=text,
        )
        for page, text in (
            (1, "先修：课程A；课程B。\n" + "这是构造的测试内容，不来自学校原文。" * 12),
            (2, "测试用评分规则：实验30%，期末70%。"),
        )
    ]


def build(blocks=None, *, profile=None, reviews=None, excluded_terms=()):
    blocks = fixture_blocks() if blocks is None else blocks
    sources = {"sample-course": SourceSnapshot("a" * 64, 2)}
    if reviews is None:
        reviews = {
            (b.source_id, b.page_number, b.block_id): review_digest(b) for b in blocks
        }
    # Test profile is synthetic, not a selected domestic retrieval configuration.
    profile = profile or ChunkProfile(100, 10, True)
    return build_reviewed_chunks(
        blocks, sources, reviews, profile, excluded_terms=excluded_terms
    )


def test_ids_are_reproducible_and_input_order_independent():
    blocks = fixture_blocks()
    assert build(blocks) == build(list(reversed(blocks))) == build(blocks)
    chunks = build(blocks)
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    assert {c.page_number for c in chunks} == {1, 2}
    assert all(len(c.text) <= 100 for c in chunks)
    assert all(c.text.startswith("课程：示例课程；编号：C101\n") for c in chunks)
    assert all(c.source_sha256 == "a" * 64 for c in chunks)


def test_content_metadata_and_profile_changes_invalidate_identity():
    original = fixture_blocks()[:1]
    baseline_ids = {c.chunk_id for c in build(original)}
    for changed in (
        replace(original[0], text=original[0].text + "新增规则。"),
        replace(original[0], course_code="C102"),
        replace(original[0], block_id="another-unit"),
    ):
        assert baseline_ids.isdisjoint(c.chunk_id for c in build([changed]))
    assert baseline_ids.isdisjoint(
        c.chunk_id for c in build(original, profile=ChunkProfile(120, 10, True))
    )


@pytest.mark.parametrize("field", ["text", "course_title", "course_code", "kind"])
def test_review_covers_metadata_as_well_as_body(field):
    block = fixture_blocks()[0]
    reviews = {
        (block.source_id, block.page_number, block.block_id): review_digest(block)
    }
    value = "assessment" if field == "kind" else "Changed"
    with pytest.raises(ValueError, match="stale"):
        build([replace(block, **{field: value})], reviews=reviews)


@pytest.mark.parametrize(
    "change",
    [
        {"source_id": "outside-scope"},
        {"source_sha256": "b" * 64},
        {"page_number": 0},
        {"page_number": 3},
        {"page_number": True},
        {"block_id": "../unsafe"},
        {"kind": "personnel"},
        {"text": "   "},
        {"course_title": "课程\n伪造字段"},
        {"course_code": "C101\nextra"},
    ],
)
def test_invalid_provenance_and_structure_are_rejected(change):
    with pytest.raises(ValueError):
        build([replace(fixture_blocks()[0], **change)])


def test_unreviewed_batch_duplicate_blocks_and_personnel_are_rejected():
    blocks = fixture_blocks()
    with pytest.raises(ValueError, match="stale"):
        build(blocks, reviews={})
    with pytest.raises(ValueError, match="Duplicate"):
        build([blocks[0], blocks[0]])
    for text in ("课程负责人：测试角色", "Taught by: Example Person"):
        with pytest.raises(ValueError, match="Privacy") as error:
            build([replace(blocks[0], text=text)])
        assert text not in str(error.value)
    with pytest.raises(ValueError, match="Privacy") as error:
        build(
            [replace(blocks[0], text="禁止导出的测试代号")],
            excluded_terms=("测试代号",),
        )
    assert "测试代号" not in str(error.value)


@pytest.mark.parametrize(
    "profile",
    [
        ChunkProfile(0, 0, False),
        ChunkProfile(100, -1, False),
        ChunkProfile(100, 100, False),
        ChunkProfile(10, 2, True),
        ChunkProfile(True, 0, False),
    ],
)
def test_total_budget_includes_header_and_profile_requires_valid_values(profile):
    with pytest.raises(ValueError):
        build(profile=profile)


def test_all_three_arms_must_share_content_and_provenance_not_just_count():
    chunks = build()
    arms = {name: chunks for name in ("dense_top5", "dense_retry", "graph_dense_retry")}
    assert_same_corpus(arms)
    assert_same_corpus({**arms, "dense_retry": list(reversed(chunks))})
    changed = [replace(chunks[0], text="silently modified"), *chunks[1:]]
    with pytest.raises(ValueError, match="same corpus"):
        assert_same_corpus({**arms, "graph_dense_retry": changed})
    with pytest.raises(ValueError, match="duplicate"):
        assert_same_corpus({**arms, "dense_retry": chunks + chunks[:1]})
    with pytest.raises(ValueError, match="three"):
        assert_same_corpus({"dense_top5": chunks})
    with pytest.raises(ValueError, match="Empty"):
        assert_same_corpus({name: [] for name in arms})
