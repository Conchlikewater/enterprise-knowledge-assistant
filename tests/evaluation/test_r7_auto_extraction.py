import json

import pytest

from evaluation.experiments.r7_auto_extraction import (
    SourceInput,
    extract,
    validate_output,
)


def source(doc="d"):
    return SourceInput(doc, "a" * 64, "c", 1, "课程甲", "先修课程：数学。学分：3。")


def payload():
    return {
        "relations": [
            {
                "predicate": "REQUIRES",
                "object_text": "数学",
                "evidence_quote": "先修课程：数学。",
            }
        ],
        "prerequisite_state": "listed",
        "prerequisite_quote": "先修课程：数学。",
    }


def test_stable_deduplicated_edges_and_source_scoped_identity():
    data = payload()
    data["relations"] *= 2
    output = validate_output(json.dumps(data), source())
    assert output["duplicates_removed"] == 1
    assert output == validate_output(json.dumps(data), source())
    other = validate_output(json.dumps(data), source("other"))
    assert other["edges"][0]["object"] != output["edges"][0]["object"]
    assert output["edges"][0]["semantic_review"] == "pending"


@pytest.mark.parametrize(
    "mutation", ["invent_quote", "invent_object", "override_page", "unknown_relation"]
)
def test_hallucinated_or_overridden_fields_rejected(mutation):
    data = payload()
    edge = data["relations"][0]
    if mutation == "invent_quote":
        edge["evidence_quote"] = "先修课程：物理。"
    elif mutation == "invent_object":
        edge["object_text"] = "物理"
    elif mutation == "override_page":
        edge["page_number"] = 999
    else:
        edge["predicate"] = "EXECUTE_SHELL"
    with pytest.raises(ValueError):
        validate_output(json.dumps(data), source())


def test_empty_is_unknown_not_explicit_none():
    data = {"relations": [], "prerequisite_state": "unknown", "prerequisite_quote": ""}
    assert (
        validate_output(json.dumps(data), source())["prerequisite_state"] == "unknown"
    )
    data["prerequisite_state"] = "explicit_none"
    with pytest.raises(ValueError):
        validate_output(json.dumps(data), source())


def test_explicit_none_needs_support_and_conflicting_edges_rejected():
    data = {
        "relations": [],
        "prerequisite_state": "explicit_none",
        "prerequisite_quote": "先修课程：无",
    }
    src = SourceInput("d", "a" * 64, "c", 1, "课程甲", "先修课程：无")
    assert validate_output(json.dumps(data), src)["edges"] == []
    data["relations"] = payload()["relations"]
    with pytest.raises(ValueError, match="state"):
        validate_output(json.dumps(data), src)


def test_controlled_fence_parsing_and_no_paid_retry():
    raw = "```json\n" + json.dumps(payload()) + "\n```"
    assert validate_output(raw, source())["edges"]
    calls = []

    def broken(*args):
        calls.append(args)
        raise RuntimeError("fake failure")

    with pytest.raises(RuntimeError):
        extract(source(), broken)
    assert len(calls) == 1


def test_real_pilot_directory_membership_error_cannot_pass_as_applicability():
    data = {
        "relations": [
            {
                "predicate": "BELONGS_TO",
                "object_text": "CE",
                "evidence_quote": "来源目录专业：CE",
            }
        ],
        "prerequisite_state": "unknown",
        "prerequisite_quote": "",
    }
    src = SourceInput("d", "a" * 64, "c", 1, "课程甲", "来源目录专业：CE")
    with pytest.raises(ValueError, match="applicability"):
        validate_output(json.dumps(data), src)
