"""Compare OpenAI and DeepSeek generation over shared synthetic retrievals."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings  # noqa: E402
from app.providers.deepseek_llm_provider import (  # noqa: E402
    DEFAULT_DEEPSEEK_MODEL,
    DeepSeekLLMProvider,
)
from app.providers.openai_embedding_provider import (  # noqa: E402
    OpenAIEmbeddingProvider,
)
from app.providers.openai_llm_provider import OpenAILLMProvider  # noqa: E402
from evaluation.llm_comparison import (  # noqa: E402
    LLMComparisonConfig,
    load_pricing_catalog,
    run_llm_comparison,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-online",
        action="store_true",
        help="Allow tracked synthetic text to be sent to OpenAI and DeepSeek.",
    )
    parser.add_argument("--max-questions", type=int, default=None)
    parser.add_argument("--openai-model", default="gpt-5.6-sol")
    parser.add_argument("--deepseek-model", default=DEFAULT_DEEPSEEK_MODEL)
    parser.add_argument("--reasoning-effort", default="none")
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("evaluation/llm_comparison_report.json"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("evaluation/llm_comparison_report.md"),
    )
    arguments = parser.parse_args()
    if not arguments.confirm_online:
        parser.error("--confirm-online is required; no network request was sent")

    settings = Settings.from_env(env_file=PROJECT_ROOT / ".env")
    if settings.openai_api_key is None:
        parser.error("OPENAI_API_KEY is not configured; no network request was sent")
    if settings.deepseek_api_key is None:
        parser.error("DEEPSEEK_API_KEY is not configured; no network request was sent")

    embedding = OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        batch_size=settings.embedding_batch_size,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    providers = (
        OpenAILLMProvider(
            api_key=settings.openai_api_key,
            model=arguments.openai_model,
            reasoning_effort=arguments.reasoning_effort,
            verbosity=settings.llm_verbosity,
            max_output_tokens=settings.llm_max_output_tokens,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
        DeepSeekLLMProvider(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=arguments.deepseek_model,
            reasoning_effort=arguments.reasoning_effort,
            verbosity=settings.llm_verbosity,
            max_output_tokens=settings.llm_max_output_tokens,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
    )
    pricing_as_of, pricing = load_pricing_catalog(
        PROJECT_ROOT / "evaluation" / "model_pricing.json"
    )
    report = run_llm_comparison(
        PROJECT_ROOT,
        embedding,
        providers,
        pricing_as_of=pricing_as_of,
        pricing=pricing,
        config=LLMComparisonConfig(max_questions=arguments.max_questions),
    )
    json_output = _resolve(arguments.json_output)
    markdown_output = _resolve(arguments.markdown_output)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    markdown_output.write_text(report.to_markdown(), encoding="utf-8")

    print("llm_comparison_completed=true")
    print(f"questions={report.question_count} documents={report.document_count}")
    for summary in report.provider_summaries:
        print(
            f"provider={summary['provider']} model={summary['model']} "
            f"quality_f1={_format(summary['reference_answer_token_f1'])} "
            f"behavior_accuracy={_format(summary['behavior_accuracy'])} "
            f"avg_latency_ms={_format(summary['average_latency_ms'])} "
            f"estimated_cost_usd={_format(summary['estimated_cost_usd'])}"
        )
    print(f"json_report={json_output}")
    print(f"markdown_report={markdown_output}")
    return 0


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _format(value: object) -> str:
    return "unavailable" if value is None else str(value)


if __name__ == "__main__":
    raise SystemExit(main())
