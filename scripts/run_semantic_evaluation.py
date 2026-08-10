"""Run the opt-in OpenAI embedding comparison against synthetic fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from functools import partial
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings  # noqa: E402
from app.providers.openai_embedding_provider import (  # noqa: E402
    OpenAIEmbeddingProvider,
)
from evaluation.semantic_experiment import run_semantic_comparison  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-online",
        action="store_true",
        help="Confirm that synthetic text may be sent to the configured embedding API.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/semantic_report.json"),
        help="JSON report path relative to the project root.",
    )
    arguments = parser.parse_args()
    if not arguments.confirm_online:
        parser.error("--confirm-online is required; no network request was sent")

    settings = Settings.from_env(env_file=PROJECT_ROOT / ".env")
    if settings.openai_api_key is None:
        parser.error("OPENAI_API_KEY is not configured; no network request was sent")

    provider_factory = partial(
        OpenAIEmbeddingProvider,
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        batch_size=settings.embedding_batch_size,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    report = run_semantic_comparison(PROJECT_ROOT, provider_factory)
    serialized = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
    output_path = arguments.output
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialized + "\n", encoding="utf-8")

    print("semantic_evaluation_completed=true")
    print(f"questions={report.question_count}")
    print(
        "baseline_recall="
        f"{report.baseline['evidence_recall_at_k']:.2%} "
        "semantic_recall="
        f"{report.semantic['evidence_recall_at_k']:.2%}"
    )
    print(
        "baseline_mrr="
        f"{report.baseline['evidence_mean_reciprocal_rank']:.4f} "
        "semantic_mrr="
        f"{report.semantic['evidence_mean_reciprocal_rank']:.4f}"
    )
    print(
        "baseline_bad_cases="
        f"{report.baseline['bad_case_count']} "
        "semantic_bad_cases="
        f"{report.semantic['bad_case_count']}"
    )
    threshold = report.threshold_analysis["recommended_threshold_on_this_dataset"]
    threshold_metrics = report.threshold_analysis["recommended_metrics"]
    print(f"candidate_refusal_threshold={threshold:.2f}")
    print(
        "candidate_evidence_recall="
        f"{threshold_metrics['evidence_recall']:.2%} "
        "candidate_rejection_rate="
        f"{threshold_metrics['unanswerable_rejection_rate']:.2%} "
        "candidate_false_refusal_rate="
        f"{threshold_metrics['answerable_false_refusal_rate']:.2%}"
    )
    print(f"report={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
