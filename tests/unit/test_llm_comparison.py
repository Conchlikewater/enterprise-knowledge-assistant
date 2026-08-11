import unittest
from collections.abc import Sequence
from pathlib import Path

from app.providers.llm_provider import (
    LLMGenerationResult,
    LLMProvider,
    LLMTokenUsage,
)
from evaluation.llm_comparison import (
    LLMComparisonConfig,
    ModelPrice,
    run_llm_comparison,
)
from evaluation.providers import HashingEmbeddingProvider

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class _ComparisonProvider(LLMProvider):
    def __init__(self, name: str, answer: str) -> None:
        self._name = name
        self.answer = answer
        self.closed = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return f"{self._name}-model"

    def generate_answer(
        self,
        question: str,
        context_blocks: Sequence[str],
    ) -> LLMGenerationResult:
        return LLMGenerationResult(
            text=self.answer,
            usage=LLMTokenUsage(
                input_tokens=100,
                cached_input_tokens=20,
                output_tokens=10,
            ),
        )

    def close(self) -> None:
        self.closed = True


class LLMComparisonTests(unittest.TestCase):
    def test_shared_retrieval_comparison_records_quality_usage_and_cost(self) -> None:
        first = _ComparisonProvider(
            "first",
            "Privileged access recertification is performed every quarter [1].",
        )
        second = _ComparisonProvider(
            "second",
            "Privileged access is checked quarterly [1].",
        )
        prices = {
            (provider.name, provider.model): ModelPrice(1.0, 0.5, 2.0)
            for provider in (first, second)
        }

        report = run_llm_comparison(
            PROJECT_ROOT,
            HashingEmbeddingProvider(),
            (first, second),
            pricing_as_of="test-date",
            pricing=prices,
            config=LLMComparisonConfig(max_questions=1),
        )

        self.assertEqual(report.question_count, 1)
        self.assertEqual(len(report.question_results[0]["providers"]), 2)
        self.assertEqual(report.provider_summaries[0]["reference_answer_token_f1"], 1.0)
        self.assertEqual(report.provider_summaries[0]["input_tokens"], 100)
        self.assertAlmostEqual(
            report.provider_summaries[0]["estimated_cost_usd"],
            0.00011,
        )
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)

    def test_comparison_requires_distinct_providers(self) -> None:
        provider = _ComparisonProvider("same", "answer [1]")
        with self.assertRaises(ValueError):
            run_llm_comparison(
                PROJECT_ROOT,
                HashingEmbeddingProvider(),
                (provider, provider),
                pricing_as_of="test-date",
                pricing={},
            )


if __name__ == "__main__":
    unittest.main()
