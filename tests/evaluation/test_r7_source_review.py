"""R7-A source-review guards, not retrieval or model-quality measurements."""

import hashlib
import json
from collections import Counter
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
R7 = ROOT / "evaluation" / "r7"


def load(name):
    return json.loads((R7 / name).read_text(encoding="utf-8"))


def report():
    return load("preparation/r7a_source_review_20260910.json")


def test_source_review_is_invalidated_by_any_input_change():
    audit = report()
    assert len(audit["inputs"]) == 6
    for entry in audit["inputs"]:
        path = ROOT / entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
    assert audit["summary"]["formal_questions_changed"] is False
    assert audit["summary"]["formal_freeze"] is False
    assert audit["summary"]["full_gold_verified"] == 0
    assert audit["execution_authorized"] is False


def test_every_formal_answer_and_refusal_locator_has_page_review():
    audit = report()
    questions = load("neuq_2023_questions_draft.json")["questions"]
    reviews = {row["question_id"]: row for row in audit["formal_reviews"]}
    assert len(reviews) == len(questions) == 100
    assert Counter(q["expected_behavior"] for q in questions) == {
        "answer": 89,
        "refuse": 11,
    }
    pages = {
        (p["source_id"], p["page_number"]): p["source_sha256"]
        for p in audit["source_review"]["pages"]
    }
    assert len(pages) == 55
    for q in questions:
        row = reviews[q["id"]]
        evidence = q["expected_evidence"] + q.get("refusal_review_sources", [])
        assert row["evidence_fields"] == [
            {k: e[k] for k in ("source_id", "page_number", "field")} for e in evidence
        ]
        for e in evidence:
            assert pages[e["source_id"], e["page_number"]] == e["source_sha256"]
            assert e["source_id"] in q["allowed_document_ids"]
        assert row["decision"] == "source_level_accepted"
        assert row["basis"] and row["full_gold_verified"] is False
    # Text screening of the full corpus is not visual review of every page.
    assert audit["source_review"]["all_605_pages_visually_reviewed"] is False


def test_reserve_pool_has_six_distinct_complete_source_tasks_not_branch_padding():
    audit = report()["multi_source_review"]
    questions = load("neuq_2023_questions_draft.json")["questions"]
    formal = [q for q in questions if q["category"] == "multi_hop"]
    assert set(audit["formal_ids"]) == {q["id"] for q in formal}
    reserves = audit["reserves"]
    assert len(formal) == 30 and len(reserves) == 6
    signatures = {
        frozenset(e for p in q["gold_path_candidates"] for e in p["edge_ids"])
        for q in formal
    }
    assert len(signatures) == 30
    ledger = load("neuq_2023_relation_candidates.json")
    nodes = {n["key"]: n for n in ledger["nodes"]}
    edges = {e["id"]: e for e in ledger["edges"]}
    for r in reserves:
        claims = {c["id"]: c for c in r["required_claims"]}
        assert len(claims) == len(r["required_claims"])
        signature = frozenset(claims)
        assert signature not in signatures
        signatures.add(signature)
        assert 2 <= len(r["allowed_document_ids"]) <= 3
        assert set(r["allowed_document_ids"]) == {
            c["source_id"] for c in claims.values()
        }
        assert set(e for p in r["required_paths"] for e in p) == claims.keys()
        for path in r["required_paths"]:
            assert 1 <= len(path) <= 3
            for left, right in pairwise(path):
                assert claims[left]["object"] == claims[right]["subject"]
        for c in claims.values():
            node = nodes[c["subject"]]
            assert c["source_id"] == node["source_id"]
            assert c["source_sha256"] == node["source_sha256"]
            assert c["page_number"] == 1 and c["chunk_id"] is None
            if c["predicate"] == "REQUIRES":
                assert all(
                    c[k] == edges[c["id"]][k]
                    for k in ("subject", "predicate", "object", "source_id", "field")
                )
            else:
                assert c["predicate"] == "HAS_CREDIT"
                assert c["value"] > 0 and c["field"] == "课程学分"
        # Removing any required source breaks at least one complete branch.
        for source_id in r["allowed_document_ids"]:
            removed = {k for k, c in claims.items() if c["source_id"] == source_id}
            assert any(removed.intersection(p) for p in r["required_paths"])
        assert r["full_gold_verified"] is False
        assert r["selection"] == "replacement_only_not_additional_formal_question"
        assert r["novelty_and_overlap"] and r["related_formal_ids"]
    assert len(signatures) == audit["source_level_candidate_count"] == 36
    assert audit["reserve_gate_passed"] is True
    assert audit["full_gold_reserve_gate_passed"] is False
    assert audit["statistical_independence_claimed"] is False


def test_development_source_review_does_not_claim_document_or_statistical_split():
    audit = report()["development_review"]
    dev = load("neuq_2023_development_questions_draft.json")["questions"]
    assert set(audit["positive_ids"]) == {q["id"] for q in dev if q["answerable"]}
    assert {r["id"] for r in audit["negative_reviews"]} == {
        q["id"] for q in dev if not q["answerable"]
    }
    assert audit["positive_target_fields_reused_by_formal"] is False
    assert audit["document_level_disjoint"] is False
    assert audit["statistical_independence_claimed"] is False
    dev_fields = {
        (e["source_id"], e["field_key"]) for q in dev for e in q["expected_evidence"]
    }
    for r in report()["multi_source_review"]["reserves"]:
        for c in r["required_claims"]:
            field = "credits" if c["predicate"] == "HAS_CREDIT" else "prerequisites"
            assert (c["source_id"], field) not in dev_fields


def test_source_conflict_and_missing_policy_are_not_definite_negative_facts():
    rows = {r["question_id"]: r for r in report()["formal_reviews"]}
    assert "两处矛盾" in rows["neuq-draft-077"]["basis"]
    assert "中文教材栏" in rows["neuq-draft-074"]["basis"]
    assert "绝对禁止" in rows["neuq-draft-020"]["basis"]
    assert "不能把缺证据当禁止" in rows["neuq-draft-078"]["basis"]
