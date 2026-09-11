"""Pure preparation helpers for reviewed R7 blocks; no raw-PDF clearance.

Review hashes bind *all* input fields. They are integrity records, not an
authentication system or proof of redaction. The caller must review source-wide
coverage and privacy before approving blocks. No questions, Gold, providers or
stores enter this interface. This module does not implement graph retrieval.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from app.document_processing.chunker import chunk_sections
from app.document_processing.loaders import DocumentSection

REPRESENTATION_VERSION = "r7-reviewed-blocks-v1"
CHUNKER_VERSION = "natural-boundaries-with-character-limit-v1"
KINDS = frozenset(
    {
        "course_information",
        "prerequisites",
        "learning_objectives",
        "teaching_content",
        "teaching_schedule",
        "teaching_method",
        "assessment",
    }
)
_ID = re.compile(r"[A-Za-z0-9_.:-]+\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_PERSONNEL_LABELS = (
    "任课教师",
    "中方课程协调人",
    "课程负责人",
    "环节负责人",
    "撰写",
    "审核人",
    "批准人",
    "taughtby",
    "coordinator",
    "checkedby",
    "approvedby",
)


@dataclass(frozen=True)
class SourceSnapshot:
    sha256: str
    page_count: int


@dataclass(frozen=True)
class ReviewedBlock:
    source_id: str
    source_sha256: str
    page_number: int
    block_id: str
    kind: str
    course_title: str
    course_code: str | None
    text: str


@dataclass(frozen=True)
class ChunkProfile:
    # Required arguments: no historical 220/30 or uncalibrated threshold default.
    chunk_size: int
    overlap: int
    identity_header: bool


@dataclass(frozen=True)
class EvidenceChunk:
    chunk_id: str
    source_id: str
    source_sha256: str
    page_number: int
    block_id: str
    block_chunk_index: int
    kind: str
    text: str
    content_sha256: str
    reviewed_block_sha256: str
    profile_sha256: str


def _digest(value: dict) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def review_digest(block: ReviewedBlock) -> str:
    """Use only after review; changed text, title, code or provenance invalidates it."""
    return _digest({"version": REPRESENTATION_VERSION, "block": asdict(block)})


def profile_digest(profile: ChunkProfile) -> str:
    return _digest(
        {
            "representation": REPRESENTATION_VERSION,
            "chunker": CHUNKER_VERSION,
            "profile": asdict(profile),
        }
    )


def _validate(
    block: ReviewedBlock,
    sources: dict[str, SourceSnapshot],
    reviews: dict[tuple[str, int, str], str],
    excluded_terms: tuple[str, ...],
) -> None:
    # Errors deliberately do not interpolate text, course names or private terms.
    source = sources.get(block.source_id)
    if (
        not source
        or not _ID.fullmatch(block.source_id)
        or not _ID.fullmatch(block.block_id)
        or not _HASH.fullmatch(block.source_sha256)
        or block.source_sha256 != source.sha256
        or type(block.page_number) is not int
        or not 1 <= block.page_number <= source.page_count
    ):
        raise ValueError("Unrecognized source or invalid provenance")
    if (
        block.kind not in KINDS
        or not block.text.strip()
        or not block.course_title.strip()
    ):
        raise ValueError("Unreviewable block structure")
    if any(c in block.course_title for c in "\r\n\x00") or (
        block.course_code is not None
        and not re.fullmatch(r"[A-Za-z0-9.-]+", block.course_code)
    ):
        raise ValueError("Invalid course identity header")
    key = (block.source_id, block.page_number, block.block_id)
    if reviews.get(key) != review_digest(block):
        raise ValueError("Missing or stale source-block review")
    text = "".join((block.course_title + block.text).split()).casefold()
    terms = _PERSONNEL_LABELS + excluded_terms
    if any("".join(term.split()).casefold() in text for term in terms if term.strip()):
        raise ValueError("Privacy review required; block was not accepted")


def build_reviewed_chunks(
    blocks: list[ReviewedBlock],
    sources: dict[str, SourceSnapshot],
    reviews: dict[tuple[str, int, str], str],
    profile: ChunkProfile,
    *,
    excluded_terms: tuple[str, ...] = (),
) -> list[EvidenceChunk]:
    """Build candidate chunks only, without assigning Gold or freezing a profile.

    No block crosses a page or a reviewed structural unit. Character budget
    includes the optional identity header. Caller-supplied exclusions supplement
    manual review; neither keyword filtering nor a matching hash proves privacy.
    """
    if (
        type(profile.chunk_size) is not int
        or type(profile.overlap) is not int
        or type(profile.identity_header) is not bool
        or not 0 <= profile.overlap < profile.chunk_size
    ):
        raise ValueError("Invalid chunk profile")
    keys = [(b.source_id, b.page_number, b.block_id) for b in blocks]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate source block")
    prepared = []
    for block in sorted(blocks, key=lambda b: (b.source_id, b.page_number, b.block_id)):
        _validate(block, sources, reviews, excluded_terms)
        header = (
            f"课程：{block.course_title}；编号：{block.course_code or '未核实'}\n"
            if profile.identity_header
            else ""
        )
        body_budget = profile.chunk_size - len(header)
        if body_budget <= profile.overlap:
            raise ValueError("Identity header leaves insufficient body budget")
        prepared.append((block, header, body_budget))
    # Nothing is emitted until validation of the entire batch has succeeded.
    chunks = []
    config_hash = profile_digest(profile)
    for block, header, body_budget in prepared:
        reviewed_hash = review_digest(block)
        document_id = uuid5(
            NAMESPACE_URL, f"r7:{block.source_id}:{block.source_sha256}"
        )
        pieces = chunk_sections(
            [DocumentSection(text=block.text, page_number=block.page_number)],
            document_id,
            f"{block.source_id}.pdf",
            body_budget,
            profile.overlap,
        )
        for index, piece in enumerate(pieces):
            text = header + piece.text
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            identity = _digest(
                {
                    "source_id": block.source_id,
                    "source_sha256": block.source_sha256,
                    "page_number": block.page_number,
                    "block_id": block.block_id,
                    "reviewed_block_sha256": reviewed_hash,
                    "profile_sha256": config_hash,
                    "block_chunk_index": index,
                    "content_sha256": content_hash,
                }
            )
            chunks.append(
                EvidenceChunk(
                    chunk_id=str(uuid5(NAMESPACE_URL, "r7-chunk:" + identity)),
                    source_id=block.source_id,
                    source_sha256=block.source_sha256,
                    page_number=block.page_number,
                    block_id=block.block_id,
                    block_chunk_index=index,
                    kind=block.kind,
                    text=text,
                    content_sha256=content_hash,
                    reviewed_block_sha256=reviewed_hash,
                    profile_sha256=config_hash,
                )
            )
    return chunks


def assert_same_corpus(
    arms: dict[
        Literal["dense_top5", "dense_retry", "graph_dense_retry"], list[EvidenceChunk]
    ],
) -> None:
    """Require identical immutable chunks, not merely matching chunk counts."""
    if set(arms) != {"dense_top5", "dense_retry", "graph_dense_retry"}:
        raise ValueError("Exactly three registered retrieval arms are required")
    snapshots = []
    for chunks in arms.values():
        snapshot = {c.chunk_id: asdict(c) for c in chunks}
        if len(snapshot) != len(chunks) or not snapshot:
            raise ValueError("Empty corpus or duplicate chunk IDs")
        snapshots.append(snapshot)
    if any(snapshot != snapshots[0] for snapshot in snapshots[1:]):
        raise ValueError("Retrieval arms do not share the same corpus")


@dataclass(frozen=True)
class PageDecision:
    source_id: str
    source_sha256: str
    page_number: int
    decision: Literal["pending", "keep", "exclude"]
    block_ids: tuple[str, ...] = ()
    exclusion_reason: str | None = None


def build_complete_corpus(
    blocks: list[ReviewedBlock],
    sources: dict[str, SourceSnapshot],
    reviews: dict[tuple[str, int, str], str],
    profile: ChunkProfile,
    page_decisions: list[PageDecision],
    *,
    excluded_terms: tuple[str, ...] = (),
) -> list[EvidenceChunk]:
    """Require an explicit decision for every original page, then build chunks.

    This prevents accidentally treating an answer-page subset as the whole
    corpus. Decisions still require human/source review: this is a completeness
    gate, not an automatic guarantee of privacy or unbiased content selection.
    """
    if not sources or any(
        not _HASH.fullmatch(s.sha256)
        or type(s.page_count) is not int
        or s.page_count < 1
        for s in sources.values()
    ):
        raise ValueError("Invalid source inventory")
    expected = {
        (source_id, page)
        for source_id, source in sources.items()
        for page in range(1, source.page_count + 1)
    }
    keys = [(d.source_id, d.page_number) for d in page_decisions]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError("Page inventory missing, duplicated or out of scope")
    declared_blocks = set()
    for decision in page_decisions:
        if (
            type(decision.page_number) is not int
            or decision.source_sha256 != sources[decision.source_id].sha256
        ):
            raise ValueError("Stale page decision")
        if decision.decision == "keep":
            if (
                not decision.block_ids
                or len(set(decision.block_ids)) != len(decision.block_ids)
                or decision.exclusion_reason is not None
            ):
                raise ValueError("Invalid retained page decision")
            declared_blocks.update(
                (decision.source_id, decision.page_number, block_id)
                for block_id in decision.block_ids
            )
        elif decision.decision == "exclude":
            if decision.block_ids or decision.exclusion_reason not in {
                "personnel_only",
                "bibliography_only",
                "administrative_only",
                "no_structural_content",
            }:
                raise ValueError("Excluded page requires a documented reason")
        else:
            raise ValueError("Unreviewed page prevents corpus admission")
    actual_blocks = {(b.source_id, b.page_number, b.block_id) for b in blocks}
    if not actual_blocks or actual_blocks != declared_blocks:
        raise ValueError("Reviewed page decisions and text blocks differ")
    return build_reviewed_chunks(
        blocks, sources, reviews, profile, excluded_terms=excluded_terms
    )
