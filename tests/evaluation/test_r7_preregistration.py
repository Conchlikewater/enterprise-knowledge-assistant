import hashlib
import json
import re
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


def test_all_matched_course_name_reviews_cover_32_links_and_31_sources():
    report = _load("preparation/matched_course_review_20260909.json")
    ledger = _load("neuq_2023_relation_candidates.json")
    assert (
        _sha256(R7_ROOT / "neuq_2023_relation_candidates.json")
        == report["ledger_sha256"]
    )
    nodes = {n["key"]: n for n in ledger["nodes"]}
    edges = {
        e["id"]: e
        for e in ledger["edges"]
        if e["predicate"] == "REQUIRES" and nodes[e["object"]].get("course_code")
    }
    assert len(report["rows"]) == len(edges) == 32
    assert {r["edge_id"] for r in report["rows"]} == edges.keys()
    source_ids = set()
    for row in report["rows"]:
        edge = edges[row["edge_id"]]
        source, target = nodes[edge["subject"]], nodes[edge["object"]]
        assert row["source_id"] == source["source_id"]
        assert row["source_sha256"] == source["source_sha256"]
        assert row["target_source_id"] == target["source_id"]
        assert row["target_sha256"] == target["source_sha256"]
        assert row["target_course_code"] == target["course_code"]
        assert row["reference_label"] == target["course_name"]
        assert row["name_basis_reviewed"] is True
        assert (
            row["official_code_mapping_verified"] is row["full_gold_verified"] is False
        )
        assert row["reference_contains_target_course_code"] is False
        source_ids.update((row["source_id"], row["target_source_id"]))
    pages = report["source_review"]
    assert set(pages["new_pages_visually_reviewed"]).isdisjoint(pages["reused_pages"])
    assert (
        set(pages["new_pages_visually_reviewed"] + pages["reused_pages"]) == source_ids
    )
    assert len(pages["new_pages_visually_reviewed"]) == 15
    assert len(pages["reused_pages"]) == 16
    assert len(source_ids) == pages["total_distinct_sources"] == 31
    assert report["summary"]["new_name_basis_reviews"] == 29
    assert report["summary"]["pending_name_basis_reviews"] == 0


def test_name_label_correction_does_not_claim_course_equivalence_or_gold_completion():
    report = _load("preparation/matched_course_review_20260909.json")
    ledger = _load("neuq_2023_relation_candidates.json")
    linux = next(n for n in ledger["nodes"] if n["key"] == "CST-S10")
    assert linux["course_name"] == "Linux操作系统及内核分析"
    assert linux["course_code"] == "3100213014"
    assert len(report["corrections"]) == 1
    assert report["corrections"][0]["after"] == linux["course_name"]
    assert report["corrections"][0]["before"] == "Linux操作系统与内核分析"
    assert report["exclusions"]["automatic_alias_merges"] == 0
    assert report["exclusions"]["course_equivalence_claimed"] is False
    assert report["question_content_changed"] is report["edge_content_changed"] is False
    assert report["execution_authorized"] is False
    assert report["summary"]["full_gold_verified"] == 0
    review = _load("revision_review.json")["identity_and_reserve_review"]
    assert review["all_matched_name_bases_reviewed"] == 32
    assert review["remaining_matched_course_links_pending"] == 0
    assert review["reserve_gate_passed"] is False


def test_cross_program_identity_review_is_partial_and_source_bound():
    report = _load("preparation/identity_reserve_review_20260909.json")
    ledger = _load("neuq_2023_relation_candidates.json")
    assert (
        _sha256(R7_ROOT / "neuq_2023_relation_candidates.json")
        == report["ledger_sha256"]
    )
    nodes = {n["key"]: n for n in ledger["nodes"]}
    edges = {e["id"]: e for e in ledger["edges"]}
    sources = {
        s["id"]: s
        for name in ("neuq_2023_source_lock.json", "neuq_2023_ce_source_lock.json")
        for s in _load(name)["documents"]
    }
    reviewed = report["checked_edges"]
    assert len(reviewed) == 3
    assert (
        len({sid for r in reviewed for sid in (r["source_id"], r["target_source_id"])})
        == 5
    )
    for item in reviewed:
        edge = edges[item["edge_id"]]
        assert item["source_id"] == nodes[edge["subject"]]["source_id"]
        assert item["target_source_id"] == nodes[edge["object"]]["source_id"]
        assert item["target_course_code"] == nodes[edge["object"]]["course_code"]
        assert item["source_sha256"] == sources[item["source_id"]]["sha256"]
        assert item["target_sha256"] == sources[item["target_source_id"]]["sha256"]
        assert item["reference_contains_target_course_code"] is False
        assert item["full_gold_verified"] is False
        assert item["target_applicable_programs"] == ["CST", "CE"]
    inventory = report["identity_inventory"]
    assert {i["edge_id"] for i in inventory} == {
        e["id"]
        for e in edges.values()
        if e["predicate"] == "REQUIRES" and nodes[e["object"]].get("course_code")
    }
    assert Counter(i["review_status"] for i in inventory) == {
        "cross_program_name_basis_checked": 3,
        "individual_identity_review_pending": 29,
    }
    assert report["execution_authorized"] is report["ledger_changed"] is False


def test_reserve_inventory_does_not_count_two_required_math_branches_as_two_tasks():
    report = _load("preparation/identity_reserve_review_20260909.json")[
        "reserve_review"
    ]
    paths = {
        p["id"]: p
        for p in _load("neuq_2023_relation_candidates.json")["candidate_paths"]
    }
    assigned = [pid for unit in report["units"] for pid in unit["path_ids"]]
    assert len(assigned) == len(set(assigned)) == report["original_paths"] == 31
    assert set(assigned) == paths.keys()
    assert len(report["units"]) == report["grouped_candidate_tasks"] == 27
    pairs = [u for u in report["units"] if len(u["path_ids"]) == 2]
    assert len(pairs) == report["paired_branch_groups"] == 4
    for unit in pairs:
        a, b = (paths[pid] for pid in unit["path_ids"])
        assert a["nodes"][:-1] == b["nodes"][:-1]
        assert {a["nodes"][-1], b["nodes"][-1]} == {"CST-A12", "CST-S05"}
        assert a["edge_ids"][:-1] == b["edge_ids"][:-1]
    assert all(unit["accepted"] is False for unit in report["units"])
    assert report["required_reserve"] == 36
    assert report["accepted_candidate_tasks"] == 0
    assert report["gate_passed"] is report["semantic_independence_verified"] is False


def test_missing_prerequisites_are_added_as_source_scoped_mentions_not_global_aliases():
    ledger = _load("neuq_2023_relation_candidates.json")
    nodes = {n["key"]: n for n in ledger["nodes"]}
    edges = {e["id"]: e for e in ledger["edges"]}
    subject = nodes["CE-A05"]
    source = next(
        s
        for s in _load("preparation/full_list_review_20260909.json")["sources"]
        if s["ledger_node_key"] == "CE-A05"
    )
    for index, label in enumerate(("线性代数", "概率论与数理统计"), start=1):
        key = f"CE-A05::prerequisite-mention-{index}"
        node = nodes[key]
        edge = edges[f"CE-A05--requires--{key}"]
        assert node["course_name"] == edge["name_in_source"] == label
        assert label in source["labels"]
        assert node["source_id"] == edge["source_id"] == subject["source_id"]
        assert node["source_sha256"] == edge["source_sha256"] == source["source_sha256"]
        assert node["course_code"] is node["canonical_course_key"] is None
        assert edge["field"] == "先修课程" and edge["page_number"] == 1
        assert not any(e["subject"] == key for e in edges.values())
    assert ledger["capacity"]["explicit_candidate_edges"] == 62
    assert ledger["capacity"]["total_candidate_edges"] == 79
    assert ledger["capacity"]["accepted_multi_hop_questions"] == 0


def test_identity_review_accounts_for_repeated_names_without_merging_codes():
    report = _load("preparation/full_list_review_20260909.json")["identity_review"]
    ledger = _load("neuq_2023_relation_candidates.json")
    groups = {}
    for node in ledger["nodes"]:
        if node.get("course_name"):
            groups.setdefault(node["course_name"], []).append(node)
    repeated = {name: ns for name, ns in groups.items() if len(ns) > 1}
    assert len(repeated) == len(report["repeated_name_groups"]) == 8
    for item in report["repeated_name_groups"]:
        ns = repeated[item["name"]]
        assert item["keys"] == [n["key"] for n in ns]
        assert item["codes"] == [n["course_code"] for n in ns]
        unresolved = [
            n
            for n in ns
            if n.get("identity_status")
            == "source_scoped_mention_unresolved_course_code"
        ]
        assert item["unresolved"] == len(unresolved)
        assert all(n["canonical_course_key"] is None for n in unresolved)
    innovation = repeated["创新创业设计基础"]
    assert {n["course_code"] for n in innovation} == {"3100113007", "3100213004"}
    assert report["automatic_merges_performed"] == 0
    assert report["all_course_identity_verified"] is False


def test_full_list_review_is_source_bound_and_matches_six_answers():
    report = _load("preparation/full_list_review_20260909.json")
    assert (
        _sha256(R7_ROOT / "neuq_2023_questions_draft.json")
        == report["question_file_sha256"]
    )
    sources = {
        s["id"]: s
        for name in ("neuq_2023_source_lock.json", "neuq_2023_ce_source_lock.json")
        for s in _load(name)["documents"]
    }
    reviewed = {s["source_id"]: s for s in report["sources"]}
    assert len(reviewed) == 11
    for sid, item in reviewed.items():
        assert item["source_sha256"] == sources[sid]["sha256"]
        assert item["page_number"] == 1
        assert item["labels"] and len(set(item["labels"])) == len(item["labels"])
        assert item["full_field_review_passed"] is True
    questions = {
        q["id"]: q for q in _load("neuq_2023_questions_draft.json")["questions"]
    }
    assert len(report["questions"]) == 6
    for item in report["questions"]:
        q = questions[item["question_id"]]
        left, right = (reviewed[sid] for sid in item["source_ids"])
        expected = [label for label in left["labels"] if label in right["labels"]]
        assert item["intersection_labels"] == expected
        assert q["expected_answer"] == "、".join(expected) + "。"
        assert set(item["source_ids"]) == {
            e["source_id"] for e in q["expected_evidence"]
        }
        assert item["full_field_answer_review_passed"] is True
        assert item["chunk_mapping_verified"] is item["full_gold_verified"] is False


def test_full_list_review_discloses_unrepresented_labels_not_just_answer_paths():
    report = _load("preparation/full_list_review_20260909.json")
    assert (
        _sha256(R7_ROOT / "neuq_2023_relation_candidates.json")
        == report["ledger_file_sha256"]
    )
    ledger = _load("neuq_2023_relation_candidates.json")
    nodes = {n["key"]: n for n in ledger["nodes"]}
    missing = {}
    for item in report["sources"]:
        represented = {
            nodes[e["object"]]["course_name"]
            for e in ledger["edges"]
            if e["subject"] == item["ledger_node_key"] and e["predicate"] == "REQUIRES"
        }
        assert represented <= set(item["labels"])
        delta = set(item["labels"]) - represented
        if delta:
            missing[item["source_id"]] = delta
    findings = report["ledger_completeness_findings"]
    assert missing == {}
    assert len(findings) == 1
    assert findings[0]["full_field_count"] == 5
    assert findings[0]["original_represented_count"] == 3
    assert findings[0]["represented_count"] == 5
    assert findings[0]["remaining_missing_labels"] == []
    assert findings[0]["resolved"] is True
    assert set(findings[0]["missing_labels"]) == {"线性代数", "概率论与数理统计"}


def test_full_list_review_does_not_merge_similar_course_names_or_freeze_gold():
    report = _load("preparation/full_list_review_20260909.json")
    sources = {s["ledger_node_key"]: s for s in report["sources"]}
    assert "信号与系统" in sources["CE-S11"]["labels"]
    assert "信号与线性系统分析" in sources["CE-S12"]["labels"]
    assert "信号与系统分析" in sources["CE-A05"]["labels"]
    q38 = next(q for q in report["questions"] if q["question_id"] == "neuq-draft-038")
    assert q38["intersection_labels"] == ["数字信号处理"]
    assert report["execution_authorized"] is False
    assert report["ledger_changed"] is True
    assert report["question_content_changed"] is False
    assert report["provider_calls"] == 0


def test_multi_source_audit_is_hash_bound_and_reproducible_from_annotations():
    report = _load("preparation/multi_source_audit_20260909.json")
    for item in report["inputs"]:
        assert _sha256(PROJECT_ROOT / item["path"]) == item["sha256"]
    questions = {
        q["id"]: q
        for q in _load("neuq_2023_questions_draft.json")["questions"]
        if q["category"] == "multi_hop"
    }
    edges = {e["id"]: e for e in _load("neuq_2023_relation_candidates.json")["edges"]}
    assert {r["question_id"] for r in report["rows"]} == questions.keys()
    assert len(report["rows"]) == len(questions) == 30
    checks = 0
    for row in report["rows"]:
        q = questions[row["question_id"]]
        paths = q["gold_path_candidates"]
        ids = sorted({edge_id for p in paths for edge_id in p["edge_ids"]})
        sources = sorted({e["source_id"] for e in q["expected_evidence"]})
        assert row["edge_ids"] == ids
        assert row["source_count"] == len(sources) >= 2
        assert row["path_count"] == len(paths)
        assert row["max_path_edges"] == max(len(p["edge_ids"]) for p in paths) <= 3
        fields = ("source_id", "page_number", "field")
        assert {tuple(e[k] for k in fields) for e in q["expected_evidence"]} == {
            tuple(edges[edge_id][k] for k in fields) for edge_id in ids
        }
        expected = [
            {
                "removed_source_id": source,
                "lost_edge_ids": [
                    eid for eid in ids if edges[eid]["source_id"] == source
                ],
                "broken_path_indexes": [
                    i
                    for i, path in enumerate(paths)
                    if any(
                        edges[eid]["source_id"] == source for eid in path["edge_ids"]
                    )
                ],
            }
            for source in sources
        ]
        assert row["source_removal_checks"] == expected
        assert all(c["lost_edge_ids"] and c["broken_path_indexes"] for c in expected)
        assert row["annotation_structure_passed"] is True
        assert row["evidence_locators_match"] is True
        assert row["semantic_necessity_verified"] is row["full_gold_verified"] is False
        checks += len(expected)
    assert checks == report["summary"]["source_removal_checks"] == 66


def test_structural_evidence_audit_does_not_approve_semantics_or_hide_shared_sources():
    report = _load("preparation/multi_source_audit_20260909.json")
    draft = _load("neuq_2023_questions_draft.json")
    flagged = {
        tuple(p["question_ids"])
        for p in draft["evidence_overlap_audit"]["flagged_pairs"]
    }
    assert {tuple(p["question_ids"]) for p in report["pair_review"]} == flagged
    assert len(flagged) == report["summary"]["source_overlap_pairs"] == 8
    assert all(p["independence_verified"] is False for p in report["pair_review"])
    assert report["summary"]["semantic_gold_verified"] == 0
    assert report["summary"]["required_reviewed_reserve"] == 36
    assert report["summary"]["reserve_gate_passed"] is False
    assert report["execution_authorized"] is report["question_content_changed"] is False
    assert report["provider_calls"] == 0
    assert (
        _load("revision_review.json")["multi_source_annotation_audit"][
            "semantic_gold_verified"
        ]
        == 0
    )


def test_domestic_subtype_proposal_covers_each_question_once_without_freezing():
    proposal = _load("preparation/subtype_proposal_20260909.json")
    review = _load("revision_review.json")
    questions = _load("neuq_2023_questions_draft.json")["questions"]
    by_id = {q["id"]: q for q in questions}
    assigned = []
    counts = Counter()
    for group in proposal["groups"]:
        assert group["target_count"] == len(group["question_ids"])
        for question_id in group["question_ids"]:
            assert by_id[question_id]["category"] == group["category"]
            assigned.append(question_id)
        counts[group["category"]] += group["target_count"]
    assert len(assigned) == len(set(assigned)) == 100
    assert set(assigned) == by_id.keys()
    assert (
        dict(counts) == proposal["category_targets"] == review["distribution_proposal"]
    )
    assert proposal["revision_direction_approved"] is True
    assert proposal["exact_counts_approved"] is True
    assert proposal["exact_counts_approved_on"] == "2026-09-09"
    assert proposal["execution_authorized"] is False
    assert (
        review["subtype_distribution_review"]["exact_revised_counts_approved"] is True
    )
    assert review["draft_quality_review_complete"] is False
    assert review["formal_experiment_authorized"] is False


def test_domestic_subtype_review_is_invalidated_by_question_or_answer_changes():
    proposal = _load("preparation/subtype_proposal_20260909.json")
    questions = _load("neuq_2023_questions_draft.json")["questions"]
    projection = [
        {field: question[field] for field in proposal["question_projection_fields"]}
        for question in questions
    ]
    digest = hashlib.sha256(
        json.dumps(
            projection, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    assert digest == proposal["question_projection_sha256"]
    assert (
        digest
        == _load("revision_review.json")["subtype_distribution_review"][
            "question_projection_sha256"
        ]
    )


def test_domestic_source_concentration_and_capacity_gate_are_not_relaxed():
    proposal = _load("preparation/subtype_proposal_20260909.json")
    questions = _load("neuq_2023_questions_draft.json")["questions"]
    counts = Counter(
        source
        for q in questions
        if q["category"] in {"ordinary_fact", "relationship"}
        for source in {e["source_id"] for e in q["expected_evidence"]}
    )
    gates = proposal["quality_gates"]
    assert (
        max(counts.values())
        <= gates["per_primary_source_ordinary_and_relationship_max"]
        == 4
    )
    assert gates["multi_source_reserve_required"] == 36
    assert gates["multi_source_reserve_verified"] is False
    assert gates["all_gold_review_complete"] is False
    groups = {group["subtype"]: group for group in proposal["groups"]}
    assert groups["three_edge_prerequisite"]["target_count"] == 3
    assert groups["prerequisite_then_attribute"]["target_count"] == 10
    # Source concentration and quota checks do not prove semantic independence.


def test_r7_assets_are_hash_locked_before_graph_implementation() -> None:
    protocol = _load("protocol.json")
    assets = protocol["frozen_assets"]

    assert protocol["status"] == "superseded_pending_100_question_review"
    assert protocol["supersession"]["old_question_set_executable"] is False
    assert protocol["authorization"] == {
        "r7_authorized": True,
        "graph_retrieval_implementation_authorized_after_preregistration": True,
        "real_provider_authorized": False,
        "development_calibration_authorized": True,
        "development_calibration_budget_usd": 0.01,
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


def test_r7_replacement_requires_review_before_freezing() -> None:
    review = _load("revision_review.json")
    assert review["status"] == "distribution_approved_corpus_under_review"
    assert review["distribution_approved"] is True
    assert review["distribution_approved_at"] == "2026-09-08"
    assert review["new_question_file"] is None
    assert review["new_question_sha256"] is None
    assert review["superseded_questions_are_executable"] is False
    assert review["formal_experiment_authorized"] is False
    distribution = review["distribution_proposal"]
    assert sum(distribution.values()) == review["target_question_count"] == 100
    assert distribution["relationship"] / 100 >= 17 / 50
    assert distribution["multi_hop"] / 100 >= 12 / 50
    assert review["development_questions_changed"] is False


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


def test_r7_domestic_source_lock_is_not_a_formal_dataset_or_open_license() -> None:
    review = _load("revision_review.json")
    source_lock = _load("neuq_2023_source_lock.json")
    path = PROJECT_ROOT / review["source_candidate_lock"]
    assert _sha256(path) == review["source_candidate_lock_sha256"]
    assert source_lock["status"] == "source_bytes_pinned_pending_evidence_audit"
    assert source_lock["official_corpus_and_100_questions_frozen"] is False
    assert review["formal_corpus_frozen"] is False
    assert review["replacement_development_provider_run_authorized"] is False
    assert source_lock["reuse"]["open_redistribution_license_found"] is False
    assert source_lock["reuse"]["external_provider_upload_authorized"] is False
    assert source_lock["raw_files_committed"] is False
    policy = source_lock["question_content_policy"]
    assert policy["teacher_names_allowed"] is False
    assert policy["verbatim_paragraphs_allowed"] is False
    assert policy["noncommercial_purpose_does_not_grant_redistribution_rights"] is True
    assert "个人求职作品集" in source_lock["usage_statement"]
    assert source_lock["verification"]["unique_question_capacity_verified"] is False
    assert source_lock["verification"]["formal_metrics_produced"] is False
    documents = source_lock["documents"]
    assert len(documents) == 27
    assert len({item["id"] for item in documents}) == 27
    assert len({item["url"] for item in documents}) == 27
    assert sum(item["pages"] for item in documents) == 370
    assert sum(item["bytes"] for item in documents) == 13143060
    assert Counter(item["catalogue_term"] for item in documents) == {
        "spring": 15,
        "autumn": 12,
    }
    for item in documents:
        assert item["url"].startswith("https://sstc.neuq.edu.cn/__local/")
        assert item["url"].endswith(".pdf")
        assert len(item["sha256"]) == 64
        assert set(item["sha256"]) <= set("0123456789abcdef")
        assert item["index_publication_date"] == "2023-09-08"


def test_r7_ce_sources_are_pinned_and_duplicate_courses_are_not_extra_evidence() -> (
    None
):
    review = _load("revision_review.json")
    base = _load("neuq_2023_source_lock.json")
    supplement = _load("neuq_2023_ce_source_lock.json")
    assert (
        _sha256(PROJECT_ROOT / review["supplementary_source_candidate_lock"])
        == (review["supplementary_source_candidate_lock_sha256"])
    )
    assert (
        _sha256(PROJECT_ROOT / supplement["base_source_lock"])
        == (supplement["base_source_lock_sha256"])
    )
    assert supplement["formal_corpus_and_questions_frozen"] is False
    assert supplement["raw_files_committed"] is False
    assert supplement["external_provider_upload_authorized"] is False
    assert supplement["open_redistribution_license_found"] is False
    assert supplement["teacher_names_allowed_in_questions_or_answers"] is False
    assert supplement["verbatim_paragraphs_allowed_in_questions_or_answers"] is False
    documents = supplement["documents"]
    assert len(documents) == 22
    assert sum(item["pages"] for item in documents) == 300
    combined = base["documents"] + documents
    assert len({item["sha256"] for item in combined}) == 49
    assert sum(item["pages"] for item in combined) == 670
    selected = base["documents"] + [
        item for item in documents if item["selected_for_candidate_work"]
    ]
    assert len(selected) == review["proposed_corpus_document_count"] == 44
    assert sum(item["pages"] for item in selected) == 605
    base_ids = {item["id"] for item in base["documents"]}
    excluded = [item for item in documents if not item["selected_for_candidate_work"]]
    assert len(excluded) == 5
    for item in excluded:
        assert item["canonical_source_id"] in base_ids
        assert item["exclusion_reason"]
    for item in documents:
        assert item["url"].startswith("https://sstc.neuq.edu.cn/__local/")
        assert not {"page_one_text", "instructors", "text", "teacher"} & item.keys()


def test_r7_relation_capacity_candidates_do_not_claim_formal_gold() -> None:
    ledger = _load("neuq_2023_relation_candidates.json")
    nodes = {item["key"]: item for item in ledger["nodes"]}
    edges = {item["id"]: item for item in ledger["edges"]}
    sources = {
        item["id"]: item
        for filename in ("neuq_2023_source_lock.json", "neuq_2023_ce_source_lock.json")
        for item in _load(filename)["documents"]
    }
    assert ledger["status"] == "manual_candidates_not_gold_not_a_retrieval_graph"
    assert len(edges) == len(ledger["edges"]) == 79
    assert Counter(edge["predicate"] for edge in edges.values()) == {
        "REQUIRES": 62,
        "HAS_CREDIT": 7,
        "OFFERED_IN": 3,
        "BELONGS_TO": 7,
    }
    assert ledger["capacity"]["unique_100_question_capacity_verified"] is False
    assert ledger["capacity"]["accepted_multi_hop_questions"] == 0
    for node in nodes.values():
        assert node["source_sha256"] == sources[node["source_id"]]["sha256"]
    for edge in edges.values():
        assert edge["source_id"] == nodes[edge["subject"]]["source_id"]
        assert edge["object"] in nodes
        assert edge["page_number"] == 1
        assert edge["chunk_id"] is None
    paths = ledger["candidate_paths"]
    assert Counter(len(path["edge_ids"]) for path in paths) == {2: 22, 3: 9}
    assert len({tuple(path["nodes"]) for path in paths}) == 31
    for path in paths:
        assert path["accepted_as_formal_question"] is False
        assert len(set(path["necessary_relation_source_ids"])) >= 2
        for (left, right), edge_id in zip(
            pairwise(path["nodes"]), path["edge_ids"], strict=True
        ):
            assert edges[edge_id]["subject"] == left
            assert edges[edge_id]["object"] == right
    # Structural checks do not prove semantic correctness or question independence.


def test_r7_domestic_draft_has_full_quota_but_is_not_a_frozen_evaluation() -> None:
    draft = _load("neuq_2023_questions_draft.json")
    review = _load("revision_review.json")
    ledger = _load("neuq_2023_relation_candidates.json")
    edges = {item["id"]: item for item in ledger["edges"]}
    sources = {
        item["id"]: item
        for filename in ("neuq_2023_source_lock.json", "neuq_2023_ce_source_lock.json")
        for item in _load(filename)["documents"]
    }
    assert draft["status"] == "complete_draft_not_frozen_not_executable"
    assert draft["execution_authorized"] is False
    assert draft["teacher_names_allowed"] is False
    assert draft["verbatim_paragraphs_allowed"] is False
    assert draft["provider_calls"] == 0
    assert review["new_question_file"] is None
    assert review["draft_is_executable"] is False
    questions = draft["questions"]
    assert len(questions) == draft["draft_question_count"] == 100
    assert review["draft_writing_complete"] is True
    assert review["draft_quality_review_complete"] is False
    assert len(questions) == review["draft_question_count"]
    assert len({item["id"] for item in questions}) == 100
    assert len({item["question"] for item in questions}) == 100
    counts = Counter(item["category"] for item in questions)
    assert counts == {
        "ordinary_fact": 20,
        "relationship": 35,
        "multi_hop": 30,
        "scope_isolation": 8,
        "unanswerable": 7,
    }
    assert draft["target_distribution"] == review["distribution_proposal"]
    for category, count in counts.items():
        assert count <= draft["target_distribution"][category]
    for item in questions:
        assert item["gold_graph_coverage_verified"] is False
        scope = set(item["allowed_document_ids"])
        assert scope and scope <= sources.keys()
        if item["expected_behavior"] == "refuse":
            assert item["expected_answer"] is None
            assert not item["expected_evidence"]
        else:
            assert item["expected_behavior"] == "answer"
            assert item["expected_answer"] and item["expected_evidence"]
        evidence_sources = set()
        for evidence in item["expected_evidence"]:
            source_id = evidence["source_id"]
            evidence_sources.add(source_id)
            assert source_id in scope
            assert evidence["source_sha256"] == sources[source_id]["sha256"]
            assert 1 <= evidence["page_number"] <= sources[source_id]["pages"]
            assert evidence["chunk_id"] is None
        if item["category"] == "multi_hop":
            assert len(evidence_sources) >= 2
            assert item["gold_path_candidates"]
        for path in item["gold_path_candidates"]:
            assert 1 <= len(path["edge_ids"]) <= 3
            for (left, right), edge_id in zip(
                pairwise(path["nodes"]), path["edge_ids"], strict=True
            ):
                assert edges[edge_id]["subject"] == left
                assert edges[edge_id]["object"] == right
                assert edges[edge_id]["source_id"] in evidence_sources


def test_r7_draft_does_not_duplicate_identical_answers_and_evidence() -> None:
    questions = _load("neuq_2023_questions_draft.json")["questions"]
    signatures = []
    for item in questions:
        if item["expected_behavior"] == "refuse":
            continue  # Deliberate scope counterfactuals are reviewed separately.
        signatures.append(
            (
                item["expected_answer"],
                tuple(
                    sorted(
                        (e["source_id"], e["page_number"], e["field"])
                        for e in item["expected_evidence"]
                    )
                ),
            )
        )
    assert len(set(signatures)) == len(signatures)
    # This catches exact duplicates, not paraphrases or statistical dependence.


def test_r7_draft_limits_primary_source_reuse_and_preserves_weight_denominators() -> (
    None
):
    questions = _load("neuq_2023_questions_draft.json")["questions"]
    primary_sources = Counter(
        item["expected_evidence"][0]["source_id"]
        for item in questions
        if item["category"] in {"ordinary_fact", "relationship"}
    )
    assert max(primary_sources.values()) <= 4
    by_id = {item["id"]: item for item in questions}
    assert by_id["neuq-draft-049"]["expected_evidence"][0]["page_number"] == 15
    assert "实验环节" in by_id["neuq-draft-050"]["review_note"]
    assert by_id["neuq-draft-051"]["expected_behavior"] == "refuse"
    assert by_id["neuq-draft-052"]["expected_answer"].startswith("15%")
    assert 0.30 * 0.50 == 0.15
    # Guard the authored arithmetic; this is not a live retrieval/LLM evaluation.


def test_r7_overlap_audit_matches_source_sets_without_claiming_independence() -> None:
    draft = _load("neuq_2023_questions_draft.json")
    audit = draft["evidence_overlap_audit"]
    assert audit["independence_verified"] is False
    questions = [q for q in draft["questions"] if q["category"] == "multi_hop"]
    expected = []
    for i, left in enumerate(questions):
        a = {e["source_id"] for e in left["expected_evidence"]}
        for right in questions[i + 1 :]:
            b = {e["source_id"] for e in right["expected_evidence"]}
            if len(a & b) / len(a | b) >= 0.5:
                expected.append(
                    {
                        "question_ids": [left["id"], right["id"]],
                        "shared_sources": len(a & b),
                        "union_sources": len(a | b),
                        "review_status": "pending_not_automatically_rejected",
                    }
                )
    assert audit["flagged_pairs"] == expected
    assert len(expected) == 8


def _draft_item_fingerprint(question: dict) -> str:
    fields = (
        "question",
        "expected_answer",
        "expected_evidence",
        "gold_path_candidates",
        "gold_declaration_candidate_ids",
        "gold_comparison_candidate",
    )
    payload = json.dumps(
        {key: question[key] for key in fields if key in question},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_r7_manual_overlap_review_is_current_but_not_freeze_approval() -> None:
    draft = _load("neuq_2023_questions_draft.json")
    questions = {q["id"]: q for q in draft["questions"]}
    audit = draft["evidence_overlap_audit"]
    review = audit["manual_review"]
    assert review["all_quality_approved"] is False
    assert audit["independence_verified"] is False
    assert {tuple(r["question_ids"]) for r in review["flagged_pair_reviews"]} == {
        tuple(r["question_ids"]) for r in audit["flagged_pairs"]
    }
    assert Counter(r["review_status"] for r in review["flagged_pair_reviews"]) == {
        "keep_provisionally": 8,
    }
    all_reviews = review["flagged_pair_reviews"] + review["additional_semantic_pairs"]
    assert len(all_reviews) == 8
    assert len({tuple(r["question_ids"]) for r in all_reviews}) == 8
    for item in all_reviews:
        assert item["reason"]
        assert item["reviewed_item_sha256"] == {
            qid: _draft_item_fingerprint(questions[qid]) for qid in item["question_ids"]
        }
    # A changed question/answer/path must not silently inherit a previous review.
    changed = dict(questions["neuq-draft-061"], expected_answer="changed")
    assert _draft_item_fingerprint(changed) != _draft_item_fingerprint(
        questions["neuq-draft-061"]
    )
    assert draft["execution_authorized"] is False
    assert _load("revision_review.json")["draft_quality_review_complete"] is False


def test_r7_semantic_review_catches_pairs_below_source_overlap_cutoff() -> None:
    draft = _load("neuq_2023_questions_draft.json")
    questions = {q["id"]: q for q in draft["questions"]}
    revision = draft["revision_history"][-1]
    questions.update({q["id"]: q for q in revision["retired_question_versions"]})
    extra = revision["previous_overlap_audit"]["manual_review"][
        "additional_semantic_pairs"
    ]
    assert len(extra) == 2
    for pair in extra:
        left, right = (questions[qid] for qid in pair["question_ids"])
        a = {e["source_id"] for e in left["expected_evidence"]}
        b = {e["source_id"] for e in right["expected_evidence"]}
        assert len(a & b) / len(a | b) < 0.5
        assert pair["review_status"] == "revision_required_before_freeze"
        for qid in pair["question_ids"]:
            assert pair["reviewed_item_sha256"][qid] == _draft_item_fingerprint(
                questions[qid]
            )
    # Preserve historical defects, even after rewriting their question versions.
    current = draft["evidence_overlap_audit"]["manual_review"]
    assert current["additional_semantic_pairs"] == []
    assert len(current["resolved_prior_risk_pairs"]) == 3
    assert current["all_quality_approved"] is False


def test_r7_graph_gap_inventory_does_not_treat_any_path_as_complete_gold() -> None:
    draft = _load("neuq_2023_questions_draft.json")
    questions = {
        q["id"]: q
        for q in draft["questions"]
        if q["category"] in {"relationship", "multi_hop"}
    }
    audit = draft["graph_representation_audit"]
    records = audit["questions"]
    assert len(records) == len(questions) == 65
    assert {r["question_id"] for r in records} == set(questions)
    counts = Counter(r["status"] for r in records)
    assert counts == {
        "paths_present_but_unverified": 63,
        "explicit_absence_candidate_unverified": 2,
    }
    assert audit["summary"] == {
        "relationship_and_multihop_questions": len(questions),
        "no_candidate_paths": 0,
        "known_partial_candidate_paths": 0,
        **dict(counts),
        "verified_complete": 0,
    }
    for record in records:
        q = questions[record["question_id"]]
        assert record["reviewed_item_sha256"] == _draft_item_fingerprint(q)
        assert q["gold_graph_coverage_verified"] is False
        assert (
            record["status"]
            in {"no_candidate_paths", "explicit_absence_candidate_unverified"}
        ) == (not q["gold_path_candidates"])
        if record["status"] == "known_partial_candidate_paths":
            assert record["missing_answer_terms"]
            assert all(
                term in q["expected_answer"] for term in record["missing_answer_terms"]
            )
    # These declarations need their own evidence semantics, not a fake None edge.
    gaps = Counter(
        r.get("gap_kind") for r in records if r["status"] == "no_candidate_paths"
    )
    assert gaps == {}


def test_r7_revised_multihop_questions_keep_distinct_source_bound_meaning() -> None:
    draft = _load("neuq_2023_questions_draft.json")
    questions = {q["id"]: q for q in draft["questions"]}
    ledger = _load("neuq_2023_relation_candidates.json")
    nodes = {n["key"]: n for n in ledger["nodes"]}
    edges = {e["id"]: e for e in ledger["edges"]}
    revision = draft["revision_history"][-1]
    assert {q["id"] for q in revision["retired_question_versions"]} == {
        "neuq-draft-035",
        "neuq-draft-061",
    }
    assert len(revision["source_pages_visually_reviewed"]) == 5
    assert revision["full_gold_approved"] is False
    sources = {
        s["id"]: s
        for file in ("neuq_2023_source_lock.json", "neuq_2023_ce_source_lock.json")
        for s in _load(file)["documents"]
    }
    for page in revision["source_pages_visually_reviewed"]:
        assert page["page_number"] == 1
        assert page["source_sha256"] == sources[page["source_id"]]["sha256"]
    review = _load("revision_review.json")["latest_draft_audit"]
    assert review["known_graph_representation_gap_questions"] == 0
    assert review["global_independence_review_complete"] is False
    assert set(review["rewritten_question_ids"]) == {
        q["id"] for q in revision["retired_question_versions"]
    }
    for old in revision["retired_question_versions"]:
        new = questions[old["id"]]
        assert new["category"] == old["category"] == "multi_hop"
        assert new["question"] != old["question"]
        assert new["expected_answer"] != old["expected_answer"]
        assert len({e["source_id"] for e in new["expected_evidence"]}) == 3
        assert new["gold_graph_coverage_verified"] is False

    contrast = questions["neuq-draft-035"]
    terminals = [nodes[p["nodes"][-1]] for p in contrast["gold_path_candidates"]]
    assert {n["course_name"] for n in terminals} == {"C程序设计基础", "C++程序设计基础"}
    for node in terminals:
        assert node["type"] == "Course"
        assert node["course_code"] is None
        assert node["canonical_course_key"] is None
        assert node["identity_status"] == "source_scoped_mention_unresolved_course_code"
        assert node["page_number"] == 1
        assert node["chunk_id"] is None
    for qid in ("neuq-draft-082", "neuq-draft-083"):
        assert len(questions[qid]["gold_path_candidates"]) == 1

    membership = questions["neuq-draft-061"]
    assert nodes["CST-S03"]["course_code"] != nodes["CE-S03"]["course_code"]
    assert len(membership["gold_path_candidates"]) == 4
    assert {p["nodes"][0] for p in membership["gold_path_candidates"]} == {
        "CST-S03",
        "CE-S03",
    }
    for path in membership["gold_path_candidates"]:
        first, last = (edges[k] for k in path["edge_ids"])
        assert first["predicate"] == "REQUIRES"
        assert last["predicate"] == "BELONGS_TO"
        assert first["source_id"] != last["source_id"]
        assert last["field"] == "适用专业"
        assert nodes[last["object"]]["type"] == "Program"
        assert nodes[last["object"]]["value"] in {"CST", "CE"}
    assert ledger["capacity"]["resolved_course_prerequisite_edges"] == 32
    assert ledger["capacity"]["source_scoped_prerequisite_mention_edges"] == 30
    assert ledger["capacity"]["total_candidate_edges"] == len(edges)


def test_r7_name_batch_covers_answer_terms_without_inventing_course_identity() -> None:
    draft = _load("neuq_2023_questions_draft.json")
    qs = {q["id"]: q for q in draft["questions"]}
    ledger = _load("neuq_2023_relation_candidates.json")
    nodes = {n["key"]: n for n in ledger["nodes"]}
    edges = {e["id"]: e for e in ledger["edges"]}
    batch = draft["representation_batches"][-1]
    assert batch["id"] == "2026-09-09-source-scoped-prerequisite-names"
    assert len(batch["question_ids"]) == 17
    assert len(batch["source_pages"]) == 16
    assert batch["question_and_answer_changed"] is False
    assert batch["full_gold_approved"] is False
    sources = {
        s["id"]: s
        for f in ("neuq_2023_source_lock.json", "neuq_2023_ce_source_lock.json")
        for s in _load(f)["documents"]
    }
    for source in batch["source_pages"]:
        assert source["page_number"] == 1
        assert source["source_sha256"] == sources[source["source_id"]]["sha256"]
    for qid in batch["question_ids"]:
        q = qs[qid]
        labels = {
            nodes[p["nodes"][-1]]["course_name"] for p in q["gold_path_candidates"]
        }
        assert labels == set(re.split("[、；。]", q["expected_answer"])) - {""}
        assert q["gold_graph_coverage_verified"] is False
    mentions = [
        n
        for n in nodes.values()
        if n.get("identity_status") == "source_scoped_mention_unresolved_course_code"
    ]
    assert len(mentions) == 30
    for n in mentions:
        assert n["course_code"] is None and n["canonical_course_key"] is None
        incoming = [e for e in edges.values() if e["object"] == n["key"]]
        assert len(incoming) == 1
        assert incoming[0]["source_id"] == n["source_id"]
        assert incoming[0]["predicate"] == "REQUIRES"
        assert not any(e["subject"] == n["key"] for e in edges.values())
    comparison = qs["neuq-draft-037"]["gold_comparison_candidate"]
    assert comparison["course_identity_equivalence_claimed"] is False
    assert comparison["source_lists_complete_gold_verified"] is False
    sets = [
        {
            nodes[e["object"]]["course_name"]
            for e in edges.values()
            if e["subject"] == subject and e["predicate"] == "REQUIRES"
        }
        for subject in comparison["subjects"]
    ]
    assert sets[0] & sets[1] == set(comparison["expected_labels"])
    assert ledger["capacity"]["unique_100_question_capacity_verified"] is False


def test_r7_refusal_review_sources_are_separate_from_answer_gold() -> None:
    draft = _load("neuq_2023_questions_draft.json")
    sources = {
        item["id"]: item
        for filename in ("neuq_2023_source_lock.json", "neuq_2023_ce_source_lock.json")
        for item in _load(filename)["documents"]
    }
    scope_questions = [
        q for q in draft["questions"] if q["category"] == "scope_isolation"
    ]
    assert Counter(q["expected_behavior"] for q in scope_questions) == {
        "answer": 4,
        "refuse": 4,
    }
    reviewed = [q for q in draft["questions"] if q.get("refusal_review_sources")]
    assert len(reviewed) == 5
    assert len({q["refusal_reason_candidate"] for q in reviewed}) == 5
    for q in reviewed:
        assert q["expected_behavior"] == "refuse"
        assert q["expected_evidence"] == []
        assert q["review_status"] == "draft_pending_gold_and_split_review"
        for e in q["refusal_review_sources"]:
            assert e["source_id"] in q["allowed_document_ids"]
            assert e["source_sha256"] == sources[e["source_id"]]["sha256"]
            assert 1 <= e["page_number"] <= sources[e["source_id"]]["pages"]
    # Review evidence explains ambiguity; it is not Gold for a definitive answer.


def test_r7_attribute_hops_require_relation_and_attribute_sources() -> None:
    draft = _load("neuq_2023_questions_draft.json")
    ledger = _load("neuq_2023_relation_candidates.json")
    nodes = {n["key"]: n for n in ledger["nodes"]}
    edges = {e["id"]: e for e in ledger["edges"]}
    questions = [
        q for q in draft["questions"] if 85 <= int(q["id"].rsplit("-", 1)[1]) <= 94
    ]
    assert len(questions) == 10
    assert ledger["capacity"]["metadata_candidate_edges"] == 17
    for q in questions:
        path = q["gold_path_candidates"][0]
        assert len(path["edge_ids"]) == 2
        first, second = (edges[key] for key in path["edge_ids"])
        assert first["predicate"] == "REQUIRES"
        assert second["predicate"] in {"HAS_CREDIT", "OFFERED_IN"}
        assert first["source_id"] != second["source_id"]
        assert {e["source_id"] for e in q["expected_evidence"]} == {
            first["source_id"],
            second["source_id"],
        }
        value = nodes[second["object"]]
        assert value["type"] in {"Credit", "Semester"}
        assert value["source_id"] == second["source_id"]
        assert value["value"] in q["expected_answer"]
        assert q["gold_graph_coverage_verified"] is False


def test_r7_declarations_and_membership_are_source_bound_not_inferred_absence() -> None:
    draft = _load("neuq_2023_questions_draft.json")
    questions = {q["id"]: q for q in draft["questions"]}
    ledger = _load("neuq_2023_relation_candidates.json")
    declarations = {a["id"]: a for a in ledger["prerequisite_declarations"]}
    assert len(declarations) == 2
    assert (
        ledger["declaration_contract"]["absence_of_edges_is_not_explicit_none"] is True
    )
    assert ledger["declaration_contract"]["empty_field_is_not_explicit_none"] is True
    for qid in ("neuq-draft-098", "neuq-draft-099"):
        q = questions[qid]
        assert q["gold_path_candidates"] == []
        assert len(q["gold_declaration_candidate_ids"]) == 1
        a = declarations[q["gold_declaration_candidate_ids"][0]]
        assert a["state"] == "explicit_none"
        assert a["prerequisite_mentions"] == []
        assert a["review_status"] == "candidate_not_formal_gold"
        assert all(a[k] == v for k, v in q["expected_evidence"][0].items())
        assert a["field"] == "先修课程"
        assert q["gold_graph_coverage_verified"] is False
        changed = dict(q, gold_declaration_candidate_ids=["wrong-source"])
        assert _draft_item_fingerprint(changed) != _draft_item_fingerprint(q)
    blank = questions["neuq-draft-074"]
    assert not blank.get("gold_declaration_candidate_ids")
    assert blank["expected_behavior"] == "refuse"
    nodes = {n["key"]: n for n in ledger["nodes"]}
    edges = {e["id"]: e for e in ledger["edges"]}
    for qid, programs in (
        ("neuq-draft-096", {"CST", "CE"}),
        ("neuq-draft-097", {"CST", "CE", "AS"}),
    ):
        q = questions[qid]
        assert {
            nodes[p["nodes"][-1]]["value"] for p in q["gold_path_candidates"]
        } == programs
        for p in q["gold_path_candidates"]:
            assert len(p["edge_ids"]) == 1
            edge = edges[p["edge_ids"][0]]
            assert edge["predicate"] == "BELONGS_TO"
            assert all(edge[k] == v for k, v in q["expected_evidence"][0].items())


def test_r7_explicit_none_is_answerable_and_not_confused_with_blank() -> None:
    draft = _load("neuq_2023_questions_draft.json")
    by_id = {q["id"]: q for q in draft["questions"]}
    for question_id in ("neuq-draft-098", "neuq-draft-099"):
        q = by_id[question_id]
        assert q["relation_semantics_candidate"] == "explicit_no_prerequisite"
        assert q["expected_behavior"] == "answer"
        assert q["expected_evidence"]
    blank = by_id["neuq-draft-074"]
    assert blank["refusal_reason_candidate"] == "blank_is_not_explicit_none"
    assert blank["expected_behavior"] == "refuse"
    for question_id in ("neuq-draft-096", "neuq-draft-097"):
        assert by_id[question_id]["relation_semantics_candidate"] == (
            "course_program_membership"
        )
        assert "CST" in by_id[question_id]["expected_answer"]
        assert "CE" in by_id[question_id]["expected_answer"]
    assert "AS" in by_id["neuq-draft-097"]["expected_answer"]


def test_r7_shared_names_do_not_bypass_program_scope_in_draft() -> None:
    questions = {
        item["id"]: item
        for item in _load("neuq_2023_questions_draft.json")["questions"]
    }
    restricted = questions["neuq-draft-018"]
    assert restricted["allowed_document_ids"] == ["neuq-ce-2023-autumn-03"]
    assert restricted["expected_behavior"] == "refuse"
    chain = questions["neuq-draft-010"]
    restricted_chain = questions["neuq-draft-016"]
    assert chain["expected_behavior"] == "answer"
    assert restricted_chain["expected_behavior"] == "refuse"
    assert set(restricted_chain["allowed_document_ids"]) < set(
        chain["allowed_document_ids"]
    )


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
