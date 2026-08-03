"""Embedding provider port. Concrete SDK adapters belong in this package later."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Stable provider name safe to include in logs."""

    @abstractmethod
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed document chunks in the same order as the supplied texts."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed one retrieval query."""
