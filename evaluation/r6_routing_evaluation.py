"""Offline evaluator for the preregistered R6 bounded-routing protocol."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from time import perf_counter_ns
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from app.domain.models import AnswerRoute, RetrievalResult
from app.services.evidence_sufficiency import EvidenceSufficiencyPolicy
from app.services.query_rewriter import RuleBasedQueryRewriter
from app.services.question_router import RuleBasedQuestionRouter
from app.services.routed_answer_service import RoutedAnswerService

ROUTE_LABELS = ("retrieve", "direct_answer", "refuse")
RETRY_LABELS = ("retry", "no_retry")


def classification_metrics(
    expected: Sequence[str],
    predicted: Sequence[str],
    labels: Sequence[str],
) -> dict[str, Any]:
    """Calculate a row-expected/column-predicted confusion matrix and F-scores."""

    if len(expected) != len(predicted):
        raise ValueError("expected and predicted must contain the same sample count")
    if not labels or len(set(labels)) != len(labels):
        raise ValueError("labels must be non-empty and unique")
    label_set = set(labels)
    unknown = (set(expected) | set(predicted)) - label_set
    if unknown:
        raise ValueError(f"unknown labels: {sorted(unknown)}")

    matrix = {actual: {prediction: 0 for prediction in labels} for actual in labels}
    for actual, prediction in zip(expected, predicted, strict=True):
        matrix[actual][prediction] += 1

    per_class: dict[str, dict[str, float | int]] = {}
    for label in labels:
        true_positive = matrix[label][label]
        false_positive = sum(
            matrix[actual][label] for actual in labels if actual != label
        )
        false_negative = sum(
            matrix[label][prediction] for prediction in labels if prediction != label
        )
        support = sum(matrix[label].values())
        precision = _safe_ratio(true_positive, true_positive + false_positive)
        recall = _safe_ratio(true_positive, true_positive + false_negative)
        f1 = _safe_ratio(2 * precision * recall, precision + recall)
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }

    total = len(expected)
    correct = sum(matrix[label][label] for label in labels)
    return {
        "confusion_matrix": matrix,
        "correct_count": correct,
        "accuracy": _safe_ratio(correct, total),
        "per_class": per_class,
        "macro_precision": fmean(
            cast(float, per_class[label]["precision"]) for label in labels
        ),
        "macro_recall": fmean(
            cast(float, per_class[label]["recall"]) for label in labels
        ),
        "macro_f1": fmean(cast(float, per_class[label]["f1"]) for label in labels),
    }


def latency_summary(milliseconds: Sequence[float]) -> dict[str, float | int | str]:
    """Summarize local rule latency without presenting it as service latency."""

    if not milliseconds:
        return {
            "sample_count": 0,
            "mean": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "max": 0.0,
            "unit": "ms",
        }
    ordered = sorted(milliseconds)
    return {
        "sample_count": len(ordered),
        "mean": round(fmean(ordered), 6),
        "p50": round(_nearest_rank(ordered, 0.50), 6),
        "p95": round(_nearest_rank(ordered, 0.95), 6),
        "max": round(ordered[-1], 6),
        "unit": "ms",
    }


def run_r6_routing_evaluation(
    project_root: Path,
    *,
    implementation_commit: str,
    legacy_v1_answer_regressions: int,
    quality_gate_evidence: str,
) -> dict[str, Any]:
    """Run the frozen rule and retry evaluation without network or model calls."""

    root = project_root.resolve()
    protocol_path = root / "evaluation" / "r6_routing_protocol.json"
    protocol = _read_json(protocol_path)
    assets = protocol["frozen_evaluation_assets"]
    route_path, route_dataset = _load_locked_asset(
        root,
        assets["route_dataset"],
        assets["route_dataset_sha256"],
    )
    retry_path, retry_dataset = _load_locked_asset(
        root,
        assets["retry_dataset"],
        assets["retry_dataset_sha256"],
    )

    router = RuleBasedQuestionRouter()
    rewriter = RuleBasedQueryRewriter()
    route_expected: list[str] = []
    route_predicted: list[str] = []
    route_latencies: list[float] = []
    rewrite_latencies: list[float] = []
    route_cases: list[dict[str, Any]] = []
    business_fact_direct_answer_violations = 0

    for sample in route_dataset["samples"]:
        started_at = perf_counter_ns()
        decision = router.route(sample["text"])
        route_latencies.append(_elapsed_ms(started_at))
        expected_route = sample["expected_route"]
        predicted_route = decision.route.value
        route_expected.append(expected_route)
        route_predicted.append(predicted_route)
        if (
            expected_route == AnswerRoute.RETRIEVE.value
            and predicted_route == AnswerRoute.DIRECT_ANSWER.value
        ):
            business_fact_direct_answer_violations += 1

        rewrite = None
        if expected_route == AnswerRoute.RETRIEVE.value:
            rewrite_started_at = perf_counter_ns()
            rewrite = rewriter.rewrite(sample["text"])
            rewrite_latencies.append(_elapsed_ms(rewrite_started_at))
        route_cases.append(
            {
                "id": sample["id"],
                "category": sample["category"],
                "expected_route": expected_route,
                "predicted_route": predicted_route,
                "route_reason": decision.reason.value,
                "correct": expected_route == predicted_route,
                "rewrite_available": rewrite is not None,
            }
        )

    routing_metrics = classification_metrics(
        route_expected,
        route_predicted,
        ROUTE_LABELS,
    )
    routing_metrics.update(
        {
            "sample_count": len(route_cases),
            "business_fact_direct_answer_violation_count": (
                business_fact_direct_answer_violations
            ),
            "route_latency_ms": latency_summary(route_latencies),
            "rewrite_latency_ms": latency_summary(rewrite_latencies),
            "cases": route_cases,
        }
    )

    evidence_policy = EvidenceSufficiencyPolicy()
    retry_expected: list[str] = []
    retry_predicted: list[str] = []
    retry_cases: list[dict[str, Any]] = []
    for case in retry_dataset["cases"]:
        results = _results_from_scores(case["id"], case["result_scores"])
        assessment = evidence_policy.assess(
            results,
            top_k=case["top_k"],
            score_threshold=case["score_threshold"],
        )
        expected_label = "retry" if case["expected_should_retry"] else "no_retry"
        predicted_label = "retry" if assessment.should_retry else "no_retry"
        retry_expected.append(expected_label)
        retry_predicted.append(predicted_label)
        retry_cases.append(
            {
                "id": case["id"],
                "expected_should_retry": case["expected_should_retry"],
                "predicted_should_retry": assessment.should_retry,
                "required_result_count": assessment.required_result_count,
                "relevant_result_count": assessment.relevant_result_count,
                "correct": expected_label == predicted_label,
            }
        )

    retry_metrics = classification_metrics(
        retry_expected,
        retry_predicted,
        RETRY_LABELS,
    )
    positive_metrics = retry_metrics["per_class"]["retry"]
    retry_metrics.update(
        {
            "case_count": len(retry_cases),
            "retry_precision": positive_metrics["precision"],
            "retry_recall": positive_metrics["recall"],
            "retry_f1": positive_metrics["f1"],
            "cases": retry_cases,
        }
    )

    constraints = _probe_orchestration_constraints(route_dataset["samples"])
    constraints["legacy_v1_answer_regression_count"] = legacy_v1_answer_regressions
    constraints["quality_gate_evidence"] = quality_gate_evidence
    thresholds = protocol["acceptance_thresholds"]
    acceptance = _acceptance_results(
        routing_metrics,
        retry_metrics,
        constraints,
        thresholds,
    )
    failed_checks = [name for name, passed in acceptance.items() if not passed]

    return {
        "schema_version": "1.0",
        "evaluation_id": "r6-bounded-routing-evaluation-v1",
        "executed_at": datetime.now(UTC).isoformat(),
        "passed": not failed_checks,
        "failed_checks": failed_checks,
        "implementation_commit": implementation_commit,
        "protocol": {
            "path": protocol_path.relative_to(root).as_posix(),
            "version": protocol["protocol_version"],
            "status_at_execution": protocol["status"],
            "source_commit_before_implementation": protocol["source_commit"],
        },
        "frozen_assets": {
            "route_dataset": route_path.relative_to(root).as_posix(),
            "route_dataset_sha256": _sha256(route_path),
            "retry_dataset": retry_path.relative_to(root).as_posix(),
            "retry_dataset_sha256": _sha256(retry_path),
        },
        "execution": {
            "controller": "deterministic_native_control_flow",
            "provider": "none",
            "network_calls": 0,
            "embedding_calls": 0,
            "llm_calls": 0,
            "router_token_count": 0,
            "router_estimated_cost_usd": 0.0,
        },
        "routing": routing_metrics,
        "retry": retry_metrics,
        "constraints": constraints,
        "acceptance": {
            "thresholds": thresholds,
            "checks": acceptance,
        },
        "limitations": [
            "The 36 routing samples and 12 retry cases are small, deterministic, "
            "hand-authored boundary fixtures.",
            "These results test the frozen R6 contract, not open-domain intent "
            "classification or production traffic.",
            "Local rule latency excludes HTTP, retrieval, embedding, and generation "
            "latency.",
            "No real provider, user document, network request, token, or paid API was "
            "used.",
            "Passing this report does not authorize or start R7.",
        ],
    }


def _probe_orchestration_constraints(
    samples: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    probe = _EmptyRetrievalProbe()
    service = RoutedAnswerService(
        cast(Any, probe),
        cast(Any, _NeverGenerateAnswer()),
    )
    scope = (
        uuid5(NAMESPACE_URL, "r6-evaluation-document-a"),
        uuid5(NAMESPACE_URL, "r6-evaluation-document-b"),
    )
    call_limit_breaches = 0
    scope_violations = 0
    cases: list[dict[str, Any]] = []

    for sample in samples:
        if sample["expected_route"] != AnswerRoute.RETRIEVE.value:
            continue
        before = len(probe.calls)
        result = service.answer(sample["text"], scope, top_k=5)
        case_calls = probe.calls[before:]
        if len(case_calls) > 2 or result.retrieval_attempts > 2:
            call_limit_breaches += 1
        case_scope_violations = sum(call[1] != scope for call in case_calls)
        scope_violations += case_scope_violations
        cases.append(
            {
                "id": sample["id"],
                "retrieval_call_count": len(case_calls),
                "reported_retrieval_attempts": result.retrieval_attempts,
                "document_scope_preserved": case_scope_violations == 0,
                "stop_reason": result.stop_reason.value,
            }
        )

    return {
        "retrieval_call_limit_breach_count": call_limit_breaches,
        "document_scope_violation_count": scope_violations,
        "probe_case_count": len(cases),
        "probe_cases": cases,
    }


class _EmptyRetrievalProbe:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[UUID, ...], int, float | None]] = []

    def search(
        self,
        query: str,
        document_ids: Sequence[UUID],
        top_k: int,
        score_threshold: float | None = None,
    ) -> list[RetrievalResult]:
        self.calls.append((query, tuple(document_ids), top_k, score_threshold))
        return []


class _NeverGenerateAnswer:
    def answer_from_evidence(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("insufficient-evidence probe must not call generation")


def _acceptance_results(
    routing: Mapping[str, Any],
    retry: Mapping[str, Any],
    constraints: Mapping[str, Any],
    thresholds: Mapping[str, int | float],
) -> dict[str, bool]:
    return {
        "routing_accuracy": (routing["accuracy"] >= thresholds["routing_accuracy_min"]),
        "routing_macro_f1": (routing["macro_f1"] >= thresholds["routing_macro_f1_min"]),
        "business_fact_direct_answer_violation": (
            routing["business_fact_direct_answer_violation_count"]
            <= thresholds["business_fact_direct_answer_violation_max"]
        ),
        "retry_trigger_accuracy": (
            retry["accuracy"] >= thresholds["retry_trigger_accuracy_min"]
        ),
        "retry_trigger_precision": (
            retry["retry_precision"] >= thresholds["retry_trigger_precision_min"]
        ),
        "retry_trigger_recall": (
            retry["retry_recall"] >= thresholds["retry_trigger_recall_min"]
        ),
        "retrieval_call_limit": (
            constraints["retrieval_call_limit_breach_count"]
            <= thresholds["retrieval_call_limit_breach_max"]
        ),
        "document_scope": (
            constraints["document_scope_violation_count"]
            <= thresholds["document_scope_violation_max"]
        ),
        "legacy_v1_answer_regression": (
            constraints["legacy_v1_answer_regression_count"]
            <= thresholds["legacy_v1_answer_regressions_max"]
        ),
    }


def _load_locked_asset(
    project_root: Path,
    relative_path: str,
    expected_sha256: str,
) -> tuple[Path, dict[str, Any]]:
    path = (project_root / relative_path).resolve()
    if not path.is_relative_to(project_root):
        raise ValueError("frozen evaluation asset must stay inside the project")
    actual_sha256 = _sha256(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"frozen asset hash mismatch for {relative_path}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )
    return path, _read_json(path)


def _results_from_scores(
    case_id: str, scores: Sequence[float]
) -> list[RetrievalResult]:
    document_id = uuid5(NAMESPACE_URL, f"r6-retry-document:{case_id}")
    return [
        RetrievalResult(
            chunk_id=uuid5(NAMESPACE_URL, f"r6-retry-chunk:{case_id}:{index}"),
            document_id=document_id,
            filename="offline-fixture.txt",
            text=f"Deterministic evidence fixture {index}.",
            score=score,
        )
        for index, score in enumerate(scores)
    ]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_ratio(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def _nearest_rank(ordered: Sequence[float], percentile: float) -> float:
    rank = max(1, int(len(ordered) * percentile + 0.999999999))
    return ordered[rank - 1]


def _elapsed_ms(started_at: int) -> float:
    return (perf_counter_ns() - started_at) / 1_000_000
