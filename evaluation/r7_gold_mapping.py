"""Propose chunk-level Gold candidates without changing frozen R7 questions.

Only one-candidate locators are automatically resolved.  Multiple candidates
remain pending for source review; lexical overlap merely orders them and never
becomes Gold by itself.  The optional text output is local-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from evaluation.r7_chunk_profile_analysis import _admitted_inputs
from evaluation.r7_corpus_contract import (
    ChunkProfile,
    build_complete_corpus,
    profile_digest,
)

FORMAL_PROFILE = ChunkProfile(1000, 150, True)


def _kind(field: str) -> str:
    if field == "先修课程":
        return "prerequisites"
    if any(
        token in field
        for token in (
            "课程学分",
            "开课学期",
            "适用专业",
            "课程编号",
            "实验学时",
            "理论学时",
            "课程属性",
        )
    ):
        return "course_information"
    if field.startswith("成绩评定"):
        return "assessment"
    if field.startswith("表") or field.startswith("知识单元"):
        return "teaching_schedule"
    if field.startswith("专业目标") or field == "整体目标":
        return "learning_objectives"
    raise ValueError(f"Unmapped structural field: {field}")


def _terms(text: str) -> set[str]:
    result = set(re.findall(r"[A-Za-z0-9]+", text.casefold()))
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        result.add(run)
        result.update(run[index : index + 2] for index in range(len(run) - 1))
    return result - {"课程", "大纲", "多少", "什么", "是否", "分别", "所提供"}


def propose(candidate: dict, admission: dict, formal: dict, *, include_text=False):
    blocks, sources, reviews, decisions = _admitted_inputs(candidate, admission)
    chunks = build_complete_corpus(blocks, sources, reviews, FORMAL_PROFILE, decisions)
    mapped, ambiguous = 0, 0
    questions = []
    for question in formal["questions"]:
        locators = []
        query_terms = _terms(
            " ".join(
                (
                    question["question"],
                    question["expected_answer"] or "",
                )
            )
        )
        for locator_index, locator in enumerate(question["expected_evidence"], 1):
            kind = _kind(locator["field"])
            candidates = [
                chunk
                for chunk in chunks
                if chunk.source_id == locator["source_id"]
                and chunk.page_number == locator["page_number"]
                and chunk.kind == kind
            ]
            if not candidates:
                raise ValueError("Evidence locator has no chunk candidates")
            ranked = sorted(
                candidates,
                key=lambda chunk: (
                    -len(query_terms & _terms(locator["field"] + " " + chunk.text)),
                    chunk.block_id,
                    chunk.block_chunk_index,
                    chunk.chunk_id,
                ),
            )
            rows = []
            for rank, chunk in enumerate(ranked, 1):
                row = {
                    "rank": rank,
                    "chunk_id": chunk.chunk_id,
                    "block_id": chunk.block_id,
                    "block_chunk_index": chunk.block_chunk_index,
                    "kind": chunk.kind,
                    "content_sha256": chunk.content_sha256,
                    "query_term_overlap": len(
                        query_terms & _terms(locator["field"] + " " + chunk.text)
                    ),
                }
                if include_text:
                    row["text"] = chunk.text
                rows.append(row)
            if len(rows) == 1:
                status, selected = "unique_candidate", [rows[0]["chunk_id"]]
                mapped += 1
            else:
                status, selected = "pending_manual_choice", []
                ambiguous += 1
            locators.append(
                {
                    "locator_index": locator_index,
                    "source_id": locator["source_id"],
                    "source_sha256": locator["source_sha256"],
                    "page_number": locator["page_number"],
                    "field": locator["field"],
                    "expected_kind": kind,
                    "status": status,
                    "selected_chunk_ids": selected,
                    "candidates": rows,
                }
            )
        questions.append(
            {
                "question_id": question["id"],
                "category": question["category"],
                "expected_behavior": question["expected_behavior"],
                "locators": locators,
            }
        )
    return {
        "schema_version": "r7-chunk-gold-proposal-v1",
        "status": ("ready_for_freeze" if ambiguous == 0 else "manual_review_required"),
        "formal_questions_sha256": hashlib.sha256(
            json.dumps(
                formal, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        "candidate_corpus_sha256": admission["output_sha256"]["candidate_corpus"],
        "profile": {
            "chunk_size": 1000,
            "overlap": 150,
            "identity_header": True,
        },
        "provider_calls": 0,
        "formal_results_used_for_parameter_selection": False,
        "summary": {
            "questions": len(formal["questions"]),
            "evidence_locators": mapped + ambiguous,
            "unique_candidate_locators": mapped,
            "manual_review_locators": ambiguous,
        },
        "questions": questions,
        "limitations": [
            "Lexical overlap orders candidates only; it is not an automatic Gold label.",
            "No retrieval scores or formal experiment outcomes were computed.",
        ],
    }


def freeze(
    proposal: dict,
    manual: dict,
    formal: dict,
    relations: dict,
    candidate: dict,
    admission: dict,
) -> dict:
    """Resolve reviewed candidates and bind formal paths to sourced assertions."""
    if (
        proposal["candidate_corpus_sha256"]
        != admission["output_sha256"]["candidate_corpus"]
        or manual["candidate_corpus_sha256"] != proposal["candidate_corpus_sha256"]
    ):
        raise ValueError("Gold inputs do not bind the admitted corpus")
    if manual["profile_sha256"] != profile_digest(FORMAL_PROFILE):
        raise ValueError("Manual decisions do not bind the selected profile")
    choices = {item["key"]: item for item in manual["choices"]}
    if len(choices) != len(manual["choices"]):
        raise ValueError("Duplicate manual Gold decision")
    pending = {
        f"{question['question_id']}:{locator['locator_index']}"
        for question in proposal["questions"]
        for locator in question["locators"]
        if locator["status"] == "pending_manual_choice"
    }
    if choices.keys() != pending:
        raise ValueError("Manual Gold decisions do not exactly cover pending locators")

    question_source = {item["id"]: item for item in formal["questions"]}
    if question_source.keys() != {
        item["question_id"] for item in proposal["questions"]
    }:
        raise ValueError("Gold proposal and formal questions differ")
    relation_edges = {item["id"]: item for item in relations["edges"]}
    all_path_edges = {
        edge_id
        for question in formal["questions"]
        for path in question["gold_path_candidates"]
        for edge_id in path["edge_ids"]
    }
    if not all_path_edges <= relation_edges.keys():
        raise ValueError("Formal graph path references an unknown assertion")

    frozen_questions = []
    for question in proposal["questions"]:
        locators = []
        for locator in question["locators"]:
            key = f"{question['question_id']}:{locator['locator_index']}"
            if locator["status"] == "unique_candidate":
                selected = locator["selected_chunk_ids"]
            else:
                selected = [choices[key]["chunk_id"]]
                candidate_ids = {row["chunk_id"] for row in locator["candidates"]}
                if selected[0] not in candidate_ids:
                    raise ValueError("Manual decision selects a non-candidate chunk")
            by_id = {row["chunk_id"]: row for row in locator["candidates"]}
            locators.append(
                {
                    "locator_index": locator["locator_index"],
                    "source_id": locator["source_id"],
                    "source_sha256": locator["source_sha256"],
                    "page_number": locator["page_number"],
                    "field": locator["field"],
                    "kind": locator["expected_kind"],
                    "chunk_ids": selected,
                    "content_sha256": [
                        by_id[item]["content_sha256"] for item in selected
                    ],
                    "selection": (
                        "structurally_unique"
                        if locator["status"] == "unique_candidate"
                        else "manual_source_review"
                    ),
                }
            )
        source = question_source[question["question_id"]]
        frozen_questions.append(
            {
                "question_id": question["question_id"],
                "category": question["category"],
                "expected_behavior": question["expected_behavior"],
                "evidence": locators,
                "gold_graph_paths": source["gold_path_candidates"],
            }
        )

    blocks, sources, reviews, decisions = _admitted_inputs(candidate, admission)
    chunks = build_complete_corpus(blocks, sources, reviews, FORMAL_PROFILE, decisions)
    by_scope: dict[tuple[str, int, str], list] = {}
    for chunk in chunks:
        by_scope.setdefault(
            (chunk.source_id, chunk.page_number, chunk.kind), []
        ).append(chunk)
    assertion_bindings = []
    for assertion in [*relations["edges"], *relations["prerequisite_declarations"]]:
        candidates = by_scope.get(
            (
                assertion["source_id"],
                assertion["page_number"],
                _kind(assertion["field"]),
            ),
            [],
        )
        if len(candidates) != 1:
            raise ValueError("Graph assertion does not map to exactly one chunk")
        chunk = candidates[0]
        if assertion.get("source_sha256") not in {None, chunk.source_sha256}:
            raise ValueError("Graph assertion source hash does not match the corpus")
        assertion_bindings.append(
            {
                "assertion_id": assertion["id"],
                "assertion_type": (
                    "edge" if assertion["id"] in relation_edges else "declaration"
                ),
                "source_id": assertion["source_id"],
                "source_sha256": chunk.source_sha256,
                "page_number": assertion["page_number"],
                "field": assertion["field"],
                "chunk_id": chunk.chunk_id,
                "content_sha256": chunk.content_sha256,
            }
        )

    category_counts = {}
    behavior_counts = {}
    for question in frozen_questions:
        category_counts[question["category"]] = (
            category_counts.get(question["category"], 0) + 1
        )
        behavior_counts[question["expected_behavior"]] = (
            behavior_counts.get(question["expected_behavior"], 0) + 1
        )
    path_questions = sum(bool(q["gold_graph_paths"]) for q in frozen_questions)
    path_instances = sum(len(q["gold_graph_paths"]) for q in frozen_questions)
    return {
        "schema_version": "r7-frozen-chunk-and-graph-gold-v1",
        "status": "gold_frozen",
        "formal_questions_sha256": proposal["formal_questions_sha256"],
        "candidate_corpus_sha256": proposal["candidate_corpus_sha256"],
        "profile_sha256": profile_digest(FORMAL_PROFILE),
        "relation_candidates_sha256": hashlib.sha256(
            json.dumps(
                relations, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        "manual_decisions_sha256": hashlib.sha256(
            json.dumps(
                manual, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        "provider_calls": 0,
        "formal_results_used_for_parameter_selection": False,
        "summary": {
            "questions": len(frozen_questions),
            "category_counts": category_counts,
            "behavior_counts": behavior_counts,
            "evidence_locators": sum(len(q["evidence"]) for q in frozen_questions),
            "evidence_locators_manually_selected": len(choices),
            "questions_with_graph_paths": path_questions,
            "graph_path_instances": path_instances,
            "graph_edges": len(relations["edges"]),
            "explicit_none_declarations": len(relations["prerequisite_declarations"]),
            "assertion_chunk_bindings": len(assertion_bindings),
        },
        "questions": frozen_questions,
        "assertion_chunk_bindings": assertion_bindings,
        "scoring_denominators": {
            "retrieval_all_with_declared_evidence": sum(
                bool(q["evidence"]) for q in frozen_questions
            ),
            "graph_path_questions": path_questions,
            "answer_refusal_all": len(frozen_questions),
            "scope_isolation_questions": category_counts.get("scope_isolation", 0),
            "citation_answer_questions": behavior_counts.get("answer", 0),
        },
        "limitations": [
            "Gold is bound to this exact corpus and profile; any change invalidates chunk IDs.",
            "Graph paths are human-authored source assertions, not automatically extracted facts.",
            "No retrieval experiment or semantic threshold calibration was run.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--formal", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-text", action="store_true")
    parser.add_argument("--manual-decisions", type=Path)
    parser.add_argument("--relations", type=Path)
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    admission = json.loads(args.admission.read_text(encoding="utf-8"))
    formal = json.loads(args.formal.read_text(encoding="utf-8"))
    report = propose(
        candidate,
        admission,
        formal,
        include_text=args.include_text,
    )
    if bool(args.manual_decisions) != bool(args.relations):
        raise ValueError("Freeze requires both manual decisions and relations")
    if args.manual_decisions:
        report = freeze(
            report,
            json.loads(args.manual_decisions.read_text(encoding="utf-8")),
            formal,
            json.loads(args.relations.read_text(encoding="utf-8")),
            candidate,
            admission,
        )
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
