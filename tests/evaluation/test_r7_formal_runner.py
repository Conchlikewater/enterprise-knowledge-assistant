import pytest

from scripts.run_r7_formal import digest, prepare


def assets():
    formal = {
        "questions": [
            {
                "id": str(i),
                "question": f"fixed question {i}",
                "allowed_document_ids": ["d"],
                "expected_answer": "not an input",
            }
            for i in range(100)
        ]
    }
    gold = {"questions": [{"question_id": str(i)} for i in range(100)]}
    protocol = {
        "phase_gate": {"r7d_formal_results_allowed": True},
        "frozen_assets": {
            "gold": {"local_reconstructed_gold_canonical_sha256": digest(gold)}
        },
    }
    return protocol, formal, gold


def test_formal_runner_strips_labels_before_retrieval():
    questions, queries = prepare(*assets())
    assert len(questions) == 100
    assert all(set(q) == {"id", "question", "allowed_document_ids"} for q in questions)
    assert all("not an input" not in q for q in queries)


def test_changed_gold_or_closed_gate_fails_before_provider():
    protocol, formal, gold = assets()
    with pytest.raises(ValueError, match="hash"):
        prepare(protocol, formal, {"questions": []})
    protocol["phase_gate"]["r7d_formal_results_allowed"] = False
    with pytest.raises(ValueError, match="gate"):
        prepare(protocol, formal, gold)


def test_duplicate_formal_ids_rejected():
    protocol, formal, gold = assets()
    formal["questions"][0]["id"] = "1"
    with pytest.raises(ValueError, match="identities"):
        prepare(protocol, formal, gold)
