"""Typed contracts for the tracked offline evaluation questions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

QuestionCategory = Literal[
    "direct",
    "multi_chunk",
    "scope_isolation",
    "unanswerable",
    "paraphrase",
    "distractor",
    "low_score",
    "ambiguous",
]
ExpectedBehavior = Literal["answer", "refuse", "clarify"]

QUESTION_CATEGORIES = {
    "direct",
    "multi_chunk",
    "scope_isolation",
    "unanswerable",
    "paraphrase",
    "distractor",
    "low_score",
    "ambiguous",
}

NON_ANSWERABLE_CATEGORIES = {"unanswerable", "ambiguous"}


@dataclass(frozen=True, slots=True)
class ExpectedEvidence:
    """One exact piece of evidence that should support an answer."""

    filename: str
    page_number: int | None
    snippet: str

    @property
    def key(self) -> tuple[str, int | None, str]:
        """Return a stable identity that is independent of generated chunk IDs."""

        return (self.filename, self.page_number, self.snippet)


@dataclass(frozen=True, slots=True)
class EvaluationQuestion:
    """Ground-truth contract for one offline evaluation question."""

    id: str
    category: QuestionCategory
    question: str
    scope: tuple[str, ...]
    answerable: bool
    expected_behavior: ExpectedBehavior
    expected_answer: str | None
    expected_evidence: tuple[ExpectedEvidence, ...]
    minimum_expected_chunks: int | None = None

    @property
    def expected_sources(self) -> tuple[str, ...]:
        """Return unique expected filenames while preserving annotation order."""

        return tuple(
            dict.fromkeys(evidence.filename for evidence in self.expected_evidence)
        )

    @property
    def expected_pages(self) -> tuple[int, ...]:
        """Return unique annotated PDF pages while preserving annotation order."""

        return tuple(
            dict.fromkeys(
                evidence.page_number
                for evidence in self.expected_evidence
                if evidence.page_number is not None
            )
        )


def load_question_contracts(path: Path) -> list[EvaluationQuestion]:
    """Load and validate the question contracts stored in ``path``."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if set(payload) != {"questions"} or not isinstance(payload["questions"], list):
        raise ValueError("evaluation manifest must contain only a questions list")
    return [_parse_question(item) for item in payload["questions"]]


def _parse_question(raw: Any) -> EvaluationQuestion:
    if not isinstance(raw, dict):
        raise ValueError("each evaluation question must be an object")

    required_fields = {
        "id",
        "category",
        "question",
        "scope",
        "answerable",
        "expected_answer",
        "expected_evidence",
    }
    optional_fields = {"minimum_expected_chunks", "expected_behavior"}
    missing_fields = required_fields - set(raw)
    unknown_fields = set(raw) - required_fields - optional_fields
    if missing_fields:
        raise ValueError(
            f"evaluation question is missing fields: {sorted(missing_fields)}"
        )
    if unknown_fields:
        raise ValueError(
            f"evaluation question has unknown fields: {sorted(unknown_fields)}"
        )

    question_id = _non_empty_string(raw["id"], "question id")
    category = raw["category"]
    if category not in QUESTION_CATEGORIES:
        raise ValueError(f"unknown category in {question_id}: {category!r}")

    question_text = _non_empty_string(
        raw["question"], f"question text in {question_id}"
    )
    scope = raw["scope"]
    if not isinstance(scope, list) or not scope:
        raise ValueError(f"scope must be a non-empty list in {question_id}")
    parsed_scope = tuple(
        _non_empty_string(item, f"scope item in {question_id}") for item in scope
    )
    if "*" in parsed_scope and parsed_scope != ("*",):
        raise ValueError(f"wildcard scope must be used alone in {question_id}")

    answerable = raw["answerable"]
    if not isinstance(answerable, bool):
        raise ValueError(f"answerable must be boolean in {question_id}")
    expected_behavior = raw.get(
        "expected_behavior",
        "answer" if answerable else "refuse",
    )
    if expected_behavior not in {"answer", "refuse", "clarify"}:
        raise ValueError(f"unknown expected_behavior in {question_id}")
    if answerable != (expected_behavior == "answer"):
        raise ValueError(f"answerable and expected_behavior disagree in {question_id}")

    expected_answer = raw["expected_answer"]
    if expected_answer is not None:
        expected_answer = _non_empty_string(
            expected_answer, f"expected answer in {question_id}"
        )

    evidence_payload = raw["expected_evidence"]
    if not isinstance(evidence_payload, list):
        raise ValueError(f"expected_evidence must be a list in {question_id}")
    expected_evidence = tuple(
        _parse_evidence(item, question_id) for item in evidence_payload
    )
    if len({item.key for item in expected_evidence}) != len(expected_evidence):
        raise ValueError(f"expected evidence must be unique in {question_id}")

    minimum_expected_chunks = raw.get("minimum_expected_chunks")
    if minimum_expected_chunks is not None and (
        isinstance(minimum_expected_chunks, bool)
        or not isinstance(minimum_expected_chunks, int)
        or minimum_expected_chunks < 1
    ):
        raise ValueError(
            f"minimum_expected_chunks must be a positive integer in {question_id}"
        )

    if expected_behavior == "answer" and (
        expected_answer is None or not expected_evidence
    ):
        raise ValueError(
            f"answerable question must define an answer and evidence in {question_id}"
        )
    if expected_behavior == "refuse" and (
        expected_answer is not None or expected_evidence
    ):
        raise ValueError(
            f"unanswerable question cannot define an answer or evidence in {question_id}"
        )
    if expected_behavior == "clarify" and (
        expected_answer is not None or len(expected_evidence) < 2
    ):
        raise ValueError(
            "clarification question must define at least two candidate evidence "
            f"items and no expected answer in {question_id}"
        )
    if (category in NON_ANSWERABLE_CATEGORIES) == answerable:
        raise ValueError(f"category and answerable disagree in {question_id}")
    if category == "ambiguous" and expected_behavior != "clarify":
        raise ValueError(
            f"ambiguous question must request clarification in {question_id}"
        )
    if category == "unanswerable" and expected_behavior != "refuse":
        raise ValueError(f"unanswerable question must request refusal in {question_id}")
    if category == "multi_chunk" and minimum_expected_chunks is None:
        raise ValueError(
            f"multi_chunk question needs minimum_expected_chunks in {question_id}"
        )
    if category != "multi_chunk" and minimum_expected_chunks is not None:
        raise ValueError(
            f"minimum_expected_chunks is only valid for multi_chunk in {question_id}"
        )

    return EvaluationQuestion(
        id=question_id,
        category=category,
        question=question_text,
        scope=parsed_scope,
        answerable=answerable,
        expected_behavior=expected_behavior,
        expected_answer=expected_answer,
        expected_evidence=expected_evidence,
        minimum_expected_chunks=minimum_expected_chunks,
    )


def _parse_evidence(raw: Any, question_id: str) -> ExpectedEvidence:
    if not isinstance(raw, dict) or set(raw) != {
        "filename",
        "page_number",
        "snippet",
    }:
        raise ValueError(
            "each expected evidence item must contain filename, page_number, "
            f"and snippet in {question_id}"
        )
    filename = _non_empty_string(raw["filename"], f"evidence filename in {question_id}")
    snippet = _non_empty_string(raw["snippet"], f"evidence snippet in {question_id}")
    page_number = raw["page_number"]
    if page_number is not None and (
        isinstance(page_number, bool)
        or not isinstance(page_number, int)
        or page_number < 1
    ):
        raise ValueError(
            f"evidence page_number must be null or a positive integer in {question_id}"
        )
    return ExpectedEvidence(
        filename=filename,
        page_number=page_number,
        snippet=snippet,
    )


def _non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()
