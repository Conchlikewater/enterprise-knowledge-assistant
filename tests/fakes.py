"""Small deterministic test doubles shared across test modules."""

from __future__ import annotations

from collections.abc import Sequence

from app.providers.embedding_provider import EmbeddingProvider


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
