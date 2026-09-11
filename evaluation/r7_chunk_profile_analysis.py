"""Analyze R7 chunk profiles against an admitted local corpus and dev fixtures.

The formal 100-question set is intentionally absent from this interface.  The
production-sized profile is retained unless it violates provenance, identity,
size or development-evidence constraints; diagnostic profiles cannot win by
looking at formal evaluation results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from evaluation.r7_corpus_contract import (
    ChunkProfile,
    PageDecision,
    ReviewedBlock,
    SourceSnapshot,
    build_complete_corpus,
    profile_digest,
)

PROFILE_CANDIDATES = {
    "compact_contextual_700_100": ChunkProfile(700, 100, True),
    "production_contextual_1000_150": ChunkProfile(1000, 150, True),
    "production_no_identity_1000_150": ChunkProfile(1000, 150, False),
}
PREFERRED_PROFILE = "production_contextual_1000_150"

FIELD_PATTERNS = {
    "credits": "学分：{value}",
    "lecture_hours": "理论学时：{value}",
    "lab_hours": "实验学时：{value}",
    "course_mode": "课程模式：{value}",
    "result_type": "成绩记载方式：{value}",
}


def _digest(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def _admitted_inputs(candidate: dict, admission: dict):
    boundary = admission.get("execution_boundary", {})
    if (
        admission.get("status") != "approved_for_local_offline_chunking_only"
        or boundary.get("safe_for_local_offline_chunking") is not True
        or boundary.get("external_provider_upload_authorized") is not False
    ):
        raise ValueError("Corpus has not passed the local-only admission gate")
    outputs = admission.get("output_sha256", {})
    if outputs.get("local_candidate") != _digest(candidate) or outputs.get(
        "candidate_corpus"
    ) != _digest(candidate.get("blocks")):
        raise ValueError("Local candidate does not match the admitted hashes")
    if (
        candidate.get("question_files_loaded") is not False
        or candidate.get("gold_loaded") is not False
        or candidate.get("provider_calls") != 0
    ):
        raise ValueError("Corpus construction was not isolated from evaluation")

    source_pages: dict[str, list[dict]] = {}
    for decision in candidate["page_decisions"]:
        source_pages.setdefault(decision["source_id"], []).append(decision)
    sources = {}
    for source_id, decisions in source_pages.items():
        hashes = {item["source_sha256"] for item in decisions}
        pages = sorted(item["page_number"] for item in decisions)
        if len(hashes) != 1 or pages != list(range(1, len(pages) + 1)):
            raise ValueError("Candidate source inventory is incomplete")
        sources[source_id] = SourceSnapshot(hashes.pop(), len(pages))

    blocks = [ReviewedBlock(**block) for block in candidate["blocks"]]
    reviews = {
        (item["source_id"], item["page_number"], item["block_id"]): item[
            "candidate_review_digest"
        ]
        for item in candidate["block_reviews"]
    }
    decisions = [
        PageDecision(
            source_id=item["source_id"],
            source_sha256=item["source_sha256"],
            page_number=item["page_number"],
            decision=item["decision"],
            block_ids=tuple(item["block_ids"]),
            exclusion_reason=item["exclusion_reason"],
        )
        for item in candidate["page_decisions"]
    ]
    return blocks, sources, reviews, decisions


def _development_mapping(chunks, questions: dict) -> dict:
    mapped, missing = [], []
    targets = 0
    for question in questions["questions"]:
        evidence = question["expected_evidence"]
        if not question["answerable"]:
            if evidence:
                raise ValueError("Unanswerable development question declares Gold")
            continue
        if not evidence:
            raise ValueError("Answerable development question has no evidence")
        for locator in evidence:
            targets += 1
            try:
                pattern = FIELD_PATTERNS[locator["field_key"]].format(
                    value=locator["expected_value"]
                )
            except KeyError as exc:
                raise ValueError("Unsupported development evidence field") from exc
            matches = [
                chunk.chunk_id
                for chunk in chunks
                if chunk.source_id == locator["source_id"]
                and chunk.page_number == locator["page_number"]
                and pattern in chunk.text
            ]
            result = {
                "question_id": question["id"],
                "source_id": locator["source_id"],
                "page_number": locator["page_number"],
                "field_key": locator["field_key"],
                "chunk_ids": matches,
            }
            mapped.append(result)
            if not matches:
                missing.append(result)
    return {
        "answerable_questions": sum(q["answerable"] for q in questions["questions"]),
        "unanswerable_questions": sum(
            not q["answerable"] for q in questions["questions"]
        ),
        "evidence_targets": targets,
        "mapped_targets": targets - len(missing),
        "missing_targets": missing,
        "mappings": mapped,
    }


def analyze(candidate: dict, admission: dict, development: dict) -> dict:
    blocks, sources, reviews, decisions = _admitted_inputs(candidate, admission)
    block_identity = {
        (block.source_id, block.page_number, block.block_id): (
            block.course_title,
            block.course_code,
        )
        for block in blocks
    }
    results = {}
    for name, profile in PROFILE_CANDIDATES.items():
        chunks = build_complete_corpus(blocks, sources, reviews, profile, decisions)
        sizes = [len(chunk.text) for chunk in chunks]
        per_block = Counter(
            (chunk.source_id, chunk.page_number, chunk.block_id) for chunk in chunks
        )
        identity_ok = 0
        for chunk in chunks:
            title, code = block_identity[
                (chunk.source_id, chunk.page_number, chunk.block_id)
            ]
            identity_ok += title in chunk.text and (code is None or code in chunk.text)
        mapping = _development_mapping(chunks, development)
        results[name] = {
            "profile": asdict(profile),
            "profile_sha256": profile_digest(profile),
            "chunks": len(chunks),
            "characters_with_repeated_headers_and_overlap": sum(sizes),
            "chunk_length": {
                "minimum": min(sizes),
                "p50": _percentile(sizes, 0.50),
                "p95": _percentile(sizes, 0.95),
                "maximum": max(sizes),
            },
            "single_chunk_blocks": sum(count == 1 for count in per_block.values()),
            "split_blocks": sum(count > 1 for count in per_block.values()),
            "maximum_chunks_per_block": max(per_block.values()),
            "chunks_with_complete_course_identity": identity_ok,
            "course_identity_rate": identity_ok / len(chunks),
            "development": mapping,
        }

    preferred = results[PREFERRED_PROFILE]
    constraints = {
        "all_development_evidence_mapped": (
            preferred["development"]["mapped_targets"]
            == preferred["development"]["evidence_targets"]
        ),
        "all_chunks_keep_course_identity": (
            preferred["chunks_with_complete_course_identity"] == preferred["chunks"]
        ),
        "chunk_size_matches_current_production": (
            preferred["profile"]["chunk_size"] == 1000
            and preferred["profile"]["overlap"] == 150
        ),
        "all_chunks_respect_character_budget": (
            preferred["chunk_length"]["maximum"] <= 1000
        ),
    }
    selected = PREFERRED_PROFILE if all(constraints.values()) else None
    return {
        "schema_version": "r7-chunk-profile-analysis-v1",
        "status": "chunk_profile_selected" if selected else "selection_blocked",
        "candidate_corpus_sha256": admission["output_sha256"]["candidate_corpus"],
        "development_questions_sha256": _digest(development),
        "formal_questions_loaded": False,
        "provider_calls": 0,
        "selection_policy": {
            "preferred_profile": PREFERRED_PROFILE,
            "rule": (
                "Retain current production 1000/150 limits and add an identity "
                "header if all dev evidence, identity and size constraints pass; "
                "diagnostic profiles cannot be selected from formal results."
            ),
            "constraints": constraints,
            "selected_profile": selected,
            "reason": (
                "Controls chunk configuration across all retrieval arms while "
                "making every independently retrieved chunk self-identifying."
            ),
        },
        "profiles": results,
        "limitations": [
            "This selects corpus representation, not the semantic score threshold.",
            "Development fixtures check structural target survival; no retrieval metric was produced.",
            "The compact and no-identity profiles are diagnostics, not formal experiment arms.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--development", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    admission = json.loads(args.admission.read_text(encoding="utf-8"))
    development = json.loads(args.development.read_text(encoding="utf-8"))
    result = analyze(candidate, admission, development)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
