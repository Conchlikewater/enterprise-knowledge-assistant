import hashlib
import json
from collections import Counter
from itertools import pairwise
from pathlib import Path

from pypdf import PdfReader

PROJECT_ROOT = Path(__file__).resolve().parents[2]
R7_ROOT = PROJECT_ROOT / "evaluation" / "r7"


def _load(filename: str) -> dict:
    return json.loads((R7_ROOT / filename).read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized(text: str) -> str:
    return " ".join(text.split())


def test_r7_assets_are_hash_locked_before_graph_implementation() -> None:
    protocol = _load("protocol.json")
    assets = protocol["frozen_assets"]

    assert protocol["status"] == "preregistered_before_graph_implementation"
    assert protocol["authorization"] == {
        "r7_authorized": True,
        "graph_retrieval_implementation_authorized_after_preregistration": True,
        "real_provider_authorized": False,
        "production_integration_authorized": False,
    }
    for path_key, hash_key in (
        ("source_manifest", "source_manifest_sha256"),
        ("fixture_manifest", "fixture_manifest_sha256"),
        ("question_set", "question_set_sha256"),
        ("development_set", "development_set_sha256"),
    ):
        path = PROJECT_ROOT / assets[path_key]
        assert path.is_file()
        assert _sha256(path) == assets[hash_key]


def test_r7_corpus_has_twelve_attributed_deterministic_pdfs() -> None:
    sources = _load("corpus_sources.json")
    manifest = _load("corpus_manifest.json")
    documents = sources["documents"]
    manifest_by_name = {item["filename"]: item for item in manifest["documents"]}

    assert sources["status"] == "frozen_before_graph_implementation"
    assert sources["license"]["spdx_like_label"] == "CC-BY-NC-SA-4.0"
    assert len(documents) == manifest["document_count"] == 12
    assert sum(document["fixture_page_count"] for document in documents) == 24
    assert len({document["source_id"] for document in documents}) == 12
    assert len({document["filename"] for document in documents}) == 12

    for document in documents:
        assert document["source_url"].startswith("https://ocw.mit.edu/courses/")
        assert "publication_date" in document
        assert document["publication_date"] is None
        assert document["publication_date_note"]
        assert document["download_checked_at"] == "2026-09-08"
        assert document["instructors"]
        assert len(document["pages"]) == document["fixture_page_count"] == 2

        fixture_path = R7_ROOT / "documents" / document["filename"]
        fixture = manifest_by_name[document["filename"]]
        assert _sha256(fixture_path) == fixture["sha256"]
        reader = PdfReader(fixture_path)
        assert len(reader.pages) == fixture["page_count"] == 2
        extracted = _normalized(
            " ".join((page.extract_text() or "") for page in reader.pages)
        )
        assert document["source_url"] in "".join(extracted.split())
        assert "creativecommons.org/licenses/by-nc-sa/4.0" in extracted


def test_r7_graph_assertions_have_valid_types_and_source_evidence() -> None:
    sources = _load("corpus_sources.json")
    contract = _load("protocol.json")["graph_contract"]
    allowed_predicates = set(contract["edge_types"])
    assertions: list[dict] = []

    for document in sources["documents"]:
        for assertion in document["graph_assertions"]:
            assertions.append(assertion)
            assert assertion["predicate"] in allowed_predicates
            assert assertion["page_number"] in {1, 2}
            page = document["pages"][assertion["page_number"] - 1]
            assert assertion["evidence_snippet"] in page
            assert ":" in assertion["subject"]
            assert ":" in assertion["object"]

    assert len(assertions) == 60
    assert len({assertion["id"] for assertion in assertions}) == 60
    assert Counter(assertion["predicate"] for assertion in assertions) == {
        "OFFERED_IN": 12,
        "BELONGS_TO": 12,
        "REQUIRES": 20,
        "SATISFIES": 8,
        "RECOMMENDS": 6,
        "HAS_CREDIT": 2,
    }


def test_r7_final_questions_are_separate_balanced_and_source_grounded() -> None:
    sources = _load("corpus_sources.json")
    payload = _load("questions.json")
    development = _load("development_questions.json")
    documents = {document["source_id"]: document for document in sources["documents"]}
    filenames = {document["filename"] for document in sources["documents"]}
    questions = payload["questions"]

    assert payload["status"] == "frozen_before_graph_implementation"
    assert len(questions) == payload["question_count"] == 50
    assert len({question["id"] for question in questions}) == 50
    assert Counter(question["category"] for question in questions) == {
        "ordinary_fact": 15,
        "relationship": 17,
        "multi_hop": 12,
        "scope_isolation": 3,
        "unanswerable": 3,
    }
    assert {question["id"] for question in questions}.isdisjoint(
        question["id"] for question in development["questions"]
    )

    for question in questions:
        scope = set(question["allowed_filenames"])
        assert scope == {"*"} or scope <= filenames
        evidence = question["expected_evidence"]
        if question["expected_behavior"] == "answer":
            assert question["expected_answer"]
            assert evidence
        else:
            assert question["expected_behavior"] == "refuse"
            assert question["expected_answer"] is None
            assert not evidence

        for item in evidence:
            document = documents[item["source_id"]]
            assert item["filename"] == document["filename"]
            assert item["snippet"] in document["pages"][item["page_number"] - 1]
            assert scope == {"*"} or item["filename"] in scope

        if question["category"] in {"relationship", "multi_hop"}:
            assert question["gold_graph_paths"]


def test_r7_gold_graph_paths_are_connected_and_reference_frozen_edges() -> None:
    sources = _load("corpus_sources.json")
    questions = _load("questions.json")["questions"]
    assertions = {
        assertion["id"]: assertion
        for document in sources["documents"]
        for assertion in document["graph_assertions"]
    }

    for question in questions:
        for path in question["gold_graph_paths"]:
            nodes = path["nodes"]
            assertion_ids = path["assertion_ids"]
            assert len(nodes) == len(assertion_ids) + 1
            for (left, right), assertion_id in zip(
                pairwise(nodes),
                assertion_ids,
                strict=True,
            ):
                edge = assertions[assertion_id]
                assert {left, right} == {edge["subject"], edge["object"]}


def test_r7_three_arms_and_promotion_gates_prevent_budget_confounding() -> None:
    protocol = _load("protocol.json")
    arms = {arm["id"]: arm for arm in protocol["retrieval_arms"]}
    retry = protocol["retry_policy"]
    thresholds = protocol["promotion_thresholds"]

    assert set(arms) == {
        "dense_top5",
        "dense_retry_5x2",
        "graph_dense_retry_5x2",
    }
    assert arms["dense_top5"]["final_unique_candidate_budget"] == 5
    assert arms["dense_retry_5x2"]["final_unique_candidate_budget"] == 10
    assert arms["graph_dense_retry_5x2"]["final_unique_candidate_budget"] == 10
    assert arms["dense_retry_5x2"]["max_rounds"] == 2
    assert arms["graph_dense_retry_5x2"]["max_rounds"] == 2
    assert arms["graph_dense_retry_5x2"]["prefusion_pool_must_be_reported"] is True
    assert retry["decision_input"].startswith("Dense results only")
    assert retry["formal_semantic_score_threshold"] is None
    assert retry["threshold_status"] == "pending_real_provider_development_calibration"
    assert retry["frozen_50_must_not_be_used_for_threshold_selection"] is True
    assert thresholds["comparison_target"].endswith("versus dense_retry_5x2")
    assert thresholds["all_gates_required"] is True
    assert thresholds["passing_does_not_authorize_app_integration"] is True


def test_r7_protocol_keeps_graph_experimental_and_provider_opt_in() -> None:
    protocol = _load("protocol.json")
    scope = protocol["scope"]
    formal = protocol["provider_modes"]["formal_comparison"]
    reporting = protocol["reporting_boundaries"]

    assert scope["location"] == "evaluation/experiments/"
    assert scope["app_changes_allowed"] is False
    assert scope["production_api_changes_allowed"] is False
    assert scope["automatic_graph_extraction_claim_allowed"] is False
    assert formal["status"] == "not_authorized_not_run"
    assert formal["requires_explicit_user_budget_approval"] is True
    assert formal["llm_generation_calls"] == 0
    assert reporting["must_report_negative_results"] is True
    assert reporting["must_not_claim_production_graphrag"] is True
    assert reporting["must_not_change_thresholds_after_viewing_frozen_results"] is True
