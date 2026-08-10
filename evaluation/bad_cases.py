"""Build a structured catalogue of retrieval and response-policy bad cases."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from evaluation.contracts import load_question_contracts


@dataclass(frozen=True, slots=True)
class BadCaseGroup:
    name: str
    failure_stage: str
    status: str
    count: int
    cases: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class BadCaseReport:
    report_version: int
    source_reports: tuple[str, ...]
    groups: tuple[BadCaseGroup, ...]
    decisions: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_reports"] = list(self.source_reports)
        payload["groups"] = []
        for group in self.groups:
            group_payload = asdict(group)
            group_payload["cases"] = list(group.cases)
            payload["groups"].append(group_payload)
        return payload


def build_bad_case_report(project_root: Path) -> BadCaseReport:
    """Summarize known failures without rerunning providers or retrieval."""

    evaluation_root = project_root / "evaluation"
    lexical = _load_json(evaluation_root / "latest_report.json")
    semantic = _load_json(evaluation_root / "semantic_report.json")
    hybrid = _load_json(evaluation_root / "semantic_hybrid_report.json")
    questions = load_question_contracts(evaluation_root / "questions.json")
    questions_by_id = {question.id: question for question in questions}

    lexical_answerable = tuple(
        _compact_question_result(result)
        for result in lexical["question_results"]
        if result["expected_behavior"] == "answer" and not result["passed"]
    )
    lexical_false_accepts = tuple(
        _compact_question_result(result)
        for result in lexical["question_results"]
        if result["expected_behavior"] == "refuse" and not result["passed"]
    )

    semantic_bad_ids = semantic["semantic"]["bad_case_ids"]
    _validate_known_ids(semantic_bad_ids, questions_by_id)
    semantic_false_accepts = tuple(
        {
            "id": question_id,
            "category": questions_by_id[question_id].category,
            "configured_threshold": semantic["semantic"]["profile"][
                "unanswerable_score_threshold"
            ],
            "dataset_candidate_threshold": semantic["threshold_analysis"][
                "recommended_threshold_on_this_dataset"
            ],
        }
        for question_id in semantic_bad_ids
        if questions_by_id[question_id].expected_behavior == "refuse"
    )
    clarification_gaps = tuple(
        {
            "id": question_id,
            "category": questions_by_id[question_id].category,
            "expected_behavior": "clarify",
        }
        for question_id in semantic_bad_ids
        if questions_by_id[question_id].expected_behavior == "clarify"
    )

    hybrid_regressions = tuple(hybrid["hybrid"]["retrieval_bad_cases"])
    _validate_known_ids(
        [case["id"] for case in hybrid_regressions],
        questions_by_id,
    )
    groups = (
        _group(
            "hashing_answerable_retrieval_misses",
            "retrieval",
            "baseline_limitation",
            lexical_answerable,
        ),
        _group(
            "hashing_refusal_false_accepts",
            "refusal_threshold",
            "baseline_limitation",
            lexical_false_accepts,
        ),
        _group(
            "semantic_refusal_false_accepts_at_old_threshold",
            "refusal_threshold",
            "synthetic_candidate_found_not_promoted",
            semantic_false_accepts,
        ),
        _group(
            "clarification_response_not_supported",
            "response_policy",
            "planned",
            clarification_gaps,
        ),
        _group(
            "semantic_hybrid_regressions",
            "retrieval_ranking",
            "rejected_experiment",
            hybrid_regressions,
        ),
    )
    return BadCaseReport(
        report_version=1,
        source_reports=(
            "evaluation/latest_report.json",
            "evaluation/semantic_report.json",
            "evaluation/semantic_hybrid_report.json",
        ),
        groups=groups,
        decisions={
            "embedding_provider": "openai:text-embedding-3-small",
            "retrieval_strategy": "semantic-dense",
            "hybrid_promoted": False,
            "hybrid_decision": "rejected_due_to_recall_and_mrr_regression",
            "production_refusal_threshold_changed": False,
            "synthetic_threshold_candidate_interval": [0.37, 0.41],
            "clarification_behavior": "planned_not_implemented",
        },
    )


def _group(
    name: str,
    failure_stage: str,
    status: str,
    cases: tuple[dict[str, Any], ...],
) -> BadCaseGroup:
    return BadCaseGroup(
        name=name,
        failure_stage=failure_stage,
        status=status,
        count=len(cases),
        cases=cases,
    )


def _compact_question_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": result["id"],
        "category": result["category"],
        "failures": result["failures"],
        "retrieved_sources": result["retrieved_sources"],
        "result_count": result["result_count"],
    }


def _validate_known_ids(
    question_ids: list[str],
    questions_by_id: dict[str, Any],
) -> None:
    unknown = set(question_ids) - set(questions_by_id)
    if unknown:
        raise ValueError(f"bad-case report contains unknown question IDs: {unknown}")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
