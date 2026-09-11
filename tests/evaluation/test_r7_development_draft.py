import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "evaluation" / "r7"


def _load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_domestic_development_draft_is_separate_and_not_executable():
    dev = _load("neuq_2023_development_questions_draft.json")
    formal = _load("neuq_2023_questions_draft.json")["questions"]
    qs = dev["questions"]
    assert len(qs) == dev["question_count"] == 10
    assert sum(q["answerable"] for q in qs) == dev["answerable_count"] == 6
    assert sum(not q["answerable"] for q in qs) == dev["unsupported_count"] == 4
    assert len({q["id"] for q in qs}) == len({q["question"] for q in qs}) == 10
    assert {q["id"] for q in qs}.isdisjoint(q["id"] for q in formal)
    assert {q["question"] for q in qs}.isdisjoint(q["question"] for q in formal)
    assert dev["execution_authorized"] is False
    assert dev["semantic_disjointness_review_complete"] is False
    assert dev["document_level_disjoint"] is False
    assert dev["provider_calls"] == 0
    assert dev["chunk_mapping_complete"] is False


def test_development_fields_do_not_reuse_formal_answer_or_refusal_fields():
    dev = _load("neuq_2023_development_questions_draft.json")
    formal = _load("neuq_2023_questions_draft.json")["questions"]
    formal_fields = {
        (e["source_id"], e["page_number"], e["field"])
        for q in formal
        for e in q["expected_evidence"] + q.get("refusal_review_sources", [])
    }
    for q in dev["questions"]:
        if q["answerable"]:
            assert q["expected_answer"] not in {qf["expected_answer"] for qf in formal}
        for e in q["expected_evidence"]:
            assert (e["source_id"], e["page_number"], e["field"]) not in formal_fields
    # Exact locator/answer checks are a guard, not a proof of semantic independence.


def test_development_evidence_is_scoped_and_hash_bound():
    dev = _load("neuq_2023_development_questions_draft.json")
    sources = {
        s["id"]: s
        for f in ("neuq_2023_source_lock.json", "neuq_2023_ce_source_lock.json")
        for s in _load(f)["documents"]
    }
    assert len(dev["source_pages_visually_reviewed"]) == 6
    for page in dev["source_pages_visually_reviewed"]:
        assert page["page_number"] == 1
        assert page["source_sha256"] == sources[page["source_id"]]["sha256"]
    for q in dev["questions"]:
        assert set(q["allowed_document_ids"]) <= sources.keys()
        if q["answerable"]:
            assert q["expected_evidence"] and q["expected_answer"]
        else:
            assert q["expected_evidence"] == [] and q["expected_answer"] is None
            assert (
                q["unsupported_reason"] and q["negative_basis_review_complete"] is False
            )
        for e in q["expected_evidence"]:
            assert e["source_id"] in q["allowed_document_ids"]
            assert e["source_sha256"] == sources[e["source_id"]]["sha256"]
            assert e["page_number"] == 1 and e["chunk_id"] is None
            assert e["expected_value"] in q["expected_answer"]


def test_development_scope_counterfactual_is_explicit_not_fake_negative_gold():
    qs = {
        q["id"]: q
        for q in _load("neuq_2023_development_questions_draft.json")["questions"]
    }
    negative = qs["neuq-dev-009"]
    positive = qs[negative["counterfactual_of"]]
    assert positive["answerable"] is True and negative["answerable"] is False
    source = negative["withheld_evidence_source_id"]
    assert source in positive["allowed_document_ids"]
    assert source not in negative["allowed_document_ids"]
    assert source in {e["source_id"] for e in positive["expected_evidence"]}
