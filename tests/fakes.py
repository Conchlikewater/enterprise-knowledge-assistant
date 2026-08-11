"""Small deterministic test doubles shared across test modules."""

from __future__ import annotations

from collections.abc import Sequence

from app.providers.embedding_provider import EmbeddingProvider
from app.providers.llm_provider import LLMGenerationResult, LLMProvider


class DeterministicEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimensions: int = 3) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self._dimensions = dimensions
        self.closed = False
        self.embedded_document_batches: list[tuple[str, ...]] = []
        self.embedded_queries: list[str] = []

    @property
    def name(self) -> str:
        return "deterministic-test"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.embedded_document_batches.append(tuple(texts))
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.embedded_queries.append(text)
        return self._vector(text)

    def close(self) -> None:
        self.closed = True

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        vector[0] = 1.0
        if self._dimensions > 1:
            vector[1] = float(len(text) % 5) / 10.0
        return vector


class DeterministicLLMProvider(LLMProvider):
    def __init__(self, answer: str = "Grounded test answer [1].") -> None:
        self.answer = answer
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self.closed = False

    @property
    def name(self) -> str:
        return "deterministic-test"

    @property
    def model(self) -> str:
        return "deterministic-answer-model"

    def generate_answer(
        self,
        question: str,
        context_blocks: Sequence[str],
    ) -> LLMGenerationResult:
        self.calls.append((question, tuple(context_blocks)))
        return LLMGenerationResult(text=self.answer)

    def close(self) -> None:
        self.closed = True
