import json

import pytest

from evaluation.experiments.r7_auto_extraction import SourceInput, validate_output
from evaluation.experiments.r7_auto_graph import assemble


def record():
    src = SourceInput("d", "a" * 64, "c", 1, "A", "学分：3；开课学期：3")
    output = {
        "relations": [
            {
                "predicate": "HAS_CREDIT",
                "object_text": "3",
                "evidence_quote": "学分：3",
            },
            {
                "predicate": "OFFERED_IN",
                "object_text": "3",
                "evidence_quote": "开课学期：3",
            },
        ],
        "prerequisite_state": "unknown",
        "prerequisite_quote": "",
    }
    return {
        "status": "validated_pending_semantic_review",
        "document_id": "d",
        "chunk_id": "c",
        "extraction": validate_output(json.dumps(output), src),
    }


def test_typed_objects_same_label_not_merged_and_graph_not_approved():
    result = assemble([record()])
    assert len(result["nodes"]) == 3
    assert {n["type"] for n in result["nodes"]} == {"Course", "Credit", "Semester"}
    assert all(n["provenance"] for n in result["nodes"])
    assert result["human_review_coverage"] == 0
    assert result["production_integration"] is False


def test_failed_chunks_never_silently_admitted():
    result = assemble([{"status": "failed"}])
    assert result["failed_chunks_excluded"] == 1
    assert result["edges"] == []


def test_provenance_forgery_in_record_fails_export():
    value = record()
    value["document_id"] = "another"
    with pytest.raises(ValueError, match="source"):
        assemble([value])
