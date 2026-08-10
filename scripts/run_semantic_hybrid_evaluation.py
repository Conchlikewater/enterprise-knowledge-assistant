"""Run the opt-in OpenAI dense-versus-hybrid retrieval experiment."""

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
from evaluation.hybrid_experiment import (  # noqa: E402
    HYBRID_EXPLORATORY_CONFIG,
    run_hybrid_comparison,
)
from evaluation.providers import CachingEmbeddingProvider  # noqa: E402
from evaluation.runner import EvaluationConfig  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-online",
        action="store_true",
        help="Confirm that synthetic text may be sent to the embedding API.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/semantic_hybrid_report.json"),
        help="JSON report path relative to the project root.",
    )
    arguments = parser.parse_args()
    if not arguments.confirm_online:
        parser.error("--confirm-online is required; no network request was sent")

    settings = Settings.from_env(env_file=PROJECT_ROOT / ".env")
    if settings.openai_api_key is None:
        parser.error("OPENAI_API_KEY is not configured; no network request was sent")

    openai_factory = partial(
        OpenAIEmbeddingProvider,
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        batch_size=settings.embedding_batch_size,
        timeout_seconds=settings.openai_timeout_seconds,
    )

    def cached_provider_factory() -> CachingEmbeddingProvider:
        return CachingEmbeddingProvider(openai_factory())

    hybrid_config = EvaluationConfig(
        name="hybrid-openai-220-30-k5",
        chunk_size=HYBRID_EXPLORATORY_CONFIG.chunk_size,
        chunk_overlap=HYBRID_EXPLORATORY_CONFIG.chunk_overlap,
        top_k=HYBRID_EXPLORATORY_CONFIG.top_k,
        unanswerable_score_threshold=0.0,
        ambiguity_score_margin=HYBRID_EXPLORATORY_CONFIG.ambiguity_score_margin,
    )
    report = run_hybrid_comparison(
        PROJECT_ROOT,
        cached_provider_factory,
        hybrid_config=hybrid_config,
    )
    output_path = arguments.output
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("semantic_hybrid_evaluation_completed=true")
    print(f"questions={report.question_count}")
    print(
        "dense="
        f"recall:{report.dense['evidence_recall_at_k']:.2%},"
        f"mrr:{report.dense['evidence_mean_reciprocal_rank']:.4f},"
        f"retrieval_bad_cases:{report.dense['retrieval_bad_case_count']}"
    )
    print(
        "hybrid="
        f"recall:{report.hybrid['evidence_recall_at_k']:.2%},"
        f"mrr:{report.hybrid['evidence_mean_reciprocal_rank']:.4f},"
        f"retrieval_bad_cases:{report.hybrid['retrieval_bad_case_count']}"
    )
    print(f"delta_vs_dense={report.delta_vs_dense}")
    threshold = report.threshold_analysis["recommended_threshold_on_this_dataset"]
    threshold_metrics = report.threshold_analysis["recommended_metrics"]
    print(f"candidate_threshold={threshold}")
    print(
        "candidate_threshold_metrics="
        f"recall:{threshold_metrics['evidence_recall']:.2%},"
        f"rejection:{threshold_metrics['unanswerable_rejection_rate']:.2%},"
        "false_refusal:"
        f"{threshold_metrics['answerable_false_refusal_rate']:.2%}"
    )
    print(
        "production_change_recommended="
        f"{str(report.production_change_recommended).lower()}"
    )
    print(f"decision_reasons={','.join(report.decision_reasons)}")
    print(f"report={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
