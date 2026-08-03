"""Vector store port; the local Qdrant adapter will implement this interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from app.domain.models import Chunk, RetrievalResult


class VectorStore(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create or validate the backing collection."""

    @abstractmethod
    def health(self) -> bool:
        """Return whether the store can serve requests."""

    @abstractmethod
    def upsert(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        """Persist aligned chunk and vector sequences."""

    @abstractmethod
    def search(
        self,
        query_vector: Sequence[float],
        document_ids: Sequence[UUID],
        limit: int,
    ) -> list[RetrievalResult]:
        """Search only within the explicitly selected document IDs."""

    @abstractmethod
    def delete_by_document(self, document_id: UUID) -> None:
        """Delete all points belonging to one document."""

    @abstractmethod
    def close(self) -> None:
        """Release local or network resources held by the store."""
