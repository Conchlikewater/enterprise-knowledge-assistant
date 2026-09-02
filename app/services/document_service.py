"""Document metadata queries and safe deletion orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from app.core.exceptions import DocumentNotFoundError, DocumentStorageError
from app.document_processing.file_validation import (
    validate_storage_path,
)
from app.domain.models import Document
from app.storage.document_repository import DocumentRepository
from app.storage.vector_store import VectorStore


class DocumentService:
    def __init__(
        self,
        document_repository: DocumentRepository,
        vector_store: VectorStore,
        upload_dir: Path,
    ) -> None:
        self._document_repository = document_repository
        self._vector_store = vector_store
        self._upload_dir = upload_dir

    def list_documents(self) -> Sequence[Document]:
        return self._document_repository.list()

    def get_document(self, document_id: UUID) -> Document:
        document = self._document_repository.get(document_id)
        if document is None:
            raise DocumentNotFoundError()
        return document

    def delete_document(self, document_id: UUID) -> None:
        document = self._document_repository.get_for_deletion(document_id)
        stored_path = self._validated_storage_path(document)
        self._vector_store.delete_by_document(document_id)
        self._delete_stored_file(stored_path)
        self._document_repository.delete(document_id)

    def _validated_storage_path(self, document: Document) -> Path:
        return validate_storage_path(
            self._upload_dir,
            document.document_id,
            document.media_type,
            document.stored_path,
        )

    @staticmethod
    def _delete_stored_file(stored_path: Path) -> None:
        try:
            stored_path.unlink(missing_ok=True)
        except OSError as exc:
            raise DocumentStorageError() from exc
