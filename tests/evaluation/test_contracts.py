import json
from pathlib import Path

import pytest

from evaluation.contracts import load_question_contracts


def _write_manifest(path: Path, question: dict[str, object]) -> None:
    path.write_text(
        json.dumps({"questions": [question]}),
        encoding="utf-8",
    )


def _answerable_question() -> dict[str, object]:
    return {
        "id": "contract-01",
        "category": "direct",
        "question": "What is the policy?",
        "scope": ["policy.txt"],
        "answerable": True,
        "expected_answer": "The policy is documented.",
        "expected_evidence": [
            {
                "filename": "policy.txt",
                "page_number": None,
                "snippet": "The policy is documented.",
            }
        ],
    }


def test_question_contract_exposes_stable_evidence_identity(tmp_path: Path) -> None:
    manifest_path = tmp_path / "questions.json"
    _write_manifest(manifest_path, _answerable_question())

    question = load_question_contracts(manifest_path)[0]

    assert question.answerable
    assert question.expected_sources == ("policy.txt",)
    assert question.expected_pages == ()
    assert question.expected_evidence[0].key == (
        "policy.txt",
        None,
        "The policy is documented.",
    )


def test_answerable_question_requires_answer_and_evidence(tmp_path: Path) -> None:
    manifest_path = tmp_path / "questions.json"
    question = _answerable_question()
    question["expected_evidence"] = []
    _write_manifest(manifest_path, question)

    with pytest.raises(ValueError, match="must define an answer and evidence"):
        load_question_contracts(manifest_path)


def test_unanswerable_question_rejects_ground_truth_evidence(tmp_path: Path) -> None:
    manifest_path = tmp_path / "questions.json"
    question = _answerable_question()
    question.update(
        {
            "category": "unanswerable",
            "answerable": False,
            "expected_answer": None,
        }
    )
    _write_manifest(manifest_path, question)

    with pytest.raises(ValueError, match="cannot define an answer or evidence"):
        load_question_contracts(manifest_path)


def test_ambiguous_question_can_require_no_answer(tmp_path: Path) -> None:
    manifest_path = tmp_path / "questions.json"
    question = _answerable_question()
    question.update(
        {
            "category": "ambiguous",
            "answerable": False,
            "expected_behavior": "clarify",
            "expected_answer": None,
            "expected_evidence": [
                {
                    "filename": "policy.txt",
                    "page_number": None,
                    "snippet": "Policy alpha is documented.",
                },
                {
                    "filename": "policy.txt",
                    "page_number": None,
                    "snippet": "Policy beta is documented.",
                },
            ],
        }
    )
    _write_manifest(manifest_path, question)

    parsed = load_question_contracts(manifest_path)[0]

    assert not parsed.answerable
    assert parsed.category == "ambiguous"
    assert parsed.expected_behavior == "clarify"
