"""Document metadata repository port; SQLite will be the first adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from app.domain.models import Document, DocumentStatus


class DocumentRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create or validate the backing repository."""

    @abstractmethod
    def health(self) -> bool:
        """Return whether the repository can serve requests."""

    @abstractmethod
    def create(self, document: Document) -> None:
        """Create a document record."""

    @abstractmethod
    def get(self, document_id: UUID) -> Document | None:
        """Return one record, or None when it does not exist."""

    @abstractmethod
    def list(self) -> Sequence[Document]:
        """Return document records without exposing stored paths to the API."""

    @abstractmethod
    def update_status(
        self,
        document_id: UUID,
        status: DocumentStatus,
        chunk_count: int,
    ) -> None:
        """Update ingestion state and the resulting chunk count."""

    @abstractmethod
    def delete(self, document_id: UUID) -> None:
        """Delete one document record."""
