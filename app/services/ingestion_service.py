"""Synchronous V1 document ingestion orchestration."""

from __future__ import annotations

import logging
from pathlib import Path
from time import monotonic
from typing import BinaryIO
from uuid import UUID, uuid4

from app.core.exceptions import DocumentParseError, DocumentRepositoryError
from app.document_processing.chunker import chunk_sections
from app.document_processing.file_storage import save_upload_stream
from app.document_processing.file_validation import (
    build_storage_path,
    validate_file,
    validate_file_identity,
)
from app.document_processing.loaders import load_document
from app.domain.models import Document, DocumentStatus
from app.providers.embedding_provider import EmbeddingProvider
from app.storage.document_repository import DocumentRepository
from app.storage.vector_store import VectorStore

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(
        self,
        document_repository: DocumentRepository,
        vector_store: VectorStore,
        embedding_provider: EmbeddingProvider,
        upload_dir: Path,
        max_upload_bytes: int,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        if embedding_provider.dimensions != vector_store.dimensions:
            raise ValueError("embedding and vector store dimensions must match")
        if max_upload_bytes <= 0:
            raise ValueError("max_upload_bytes must be positive")
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if not 0 <= chunk_overlap < chunk_size:
            raise ValueError(
                "chunk_overlap must be non-negative and smaller than chunk_size"
            )

        self._document_repository = document_repository
        self._vector_store = vector_store
        self._embedding_provider = embedding_provider
        self._upload_dir = upload_dir
        self._max_upload_bytes = max_upload_bytes
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def ingest(
        self,
        source: BinaryIO,
        filename: str,
        media_type: str,
    ) -> Document:
        """Store, parse, embed, and index one document with compensating rollback."""
        identity = validate_file_identity(filename, media_type)
        document_id = uuid4()
        stored_path = build_storage_path(
            self._upload_dir,
            document_id,
            identity.suffix,
        )
        record_created = False
        started_at = monotonic()

        try:
            stored_file = save_upload_stream(
                source,
                stored_path,
                max_upload_bytes=self._max_upload_bytes,
            )
            validated_file = validate_file(
                identity.filename,
                identity.media_type,
                stored_file.size_bytes,
                self._max_upload_bytes,
            )
            document = Document(
                document_id=document_id,
                filename=validated_file.filename,
                media_type=validated_file.media_type,
                size_bytes=validated_file.size_bytes,
                sha256=stored_file.sha256,
                status=DocumentStatus.PROCESSING,
                stored_path=stored_path,
            )
            self._document_repository.create(document)
            record_created = True

            sections = load_document(stored_path, validated_file.media_type)
            chunks = chunk_sections(
                sections,
                document_id=document_id,
                filename=validated_file.filename,
                chunk_size=self._chunk_size,
                chunk_overlap=self._chunk_overlap,
            )
            if not chunks:
                raise DocumentParseError()

            vectors = self._embedding_provider.embed_documents(
                [chunk.text for chunk in chunks]
            )
            self._vector_store.upsert(chunks, vectors)
            self._document_repository.update_status(
                document_id,
                DocumentStatus.READY,
                len(chunks),
            )
            ready_document = self._document_repository.get(document_id)
            if ready_document is None:
                raise DocumentRepositoryError()

            logger.info(
                "document_ingestion_succeeded document_id=%s media_type=%s "
                "size_bytes=%d chunk_count=%d elapsed_ms=%d",
                document_id,
                validated_file.media_type,
                validated_file.size_bytes,
                len(chunks),
                int((monotonic() - started_at) * 1000),
            )
            return ready_document
        except Exception as exc:
            if record_created:
                self._rollback_record(document_id)
            self._remove_stored_file(stored_path, document_id)
            logger.warning(
                "document_ingestion_failed document_id=%s media_type=%s "
                "error_type=%s elapsed_ms=%d",
                document_id,
                identity.media_type,
                type(exc).__name__,
                int((monotonic() - started_at) * 1000),
            )
            raise

    def _rollback_record(self, document_id: UUID) -> None:
        try:
            self._vector_store.delete_by_document(document_id)
        except Exception as exc:
            logger.error(
                "document_ingestion_vector_rollback_failed "
                "document_id=%s error_type=%s",
                document_id,
                type(exc).__name__,
            )

        try:
            self._document_repository.update_status(
                document_id,
                DocumentStatus.FAILED,
                0,
            )
        except Exception as exc:
            logger.error(
                "document_ingestion_record_rollback_failed "
                "document_id=%s error_type=%s",
                document_id,
                type(exc).__name__,
            )

    @staticmethod
    def _remove_stored_file(stored_path: Path, document_id: UUID) -> None:
        try:
            stored_path.unlink(missing_ok=True)
        except OSError as exc:
            logger.error(
                "document_ingestion_file_rollback_failed "
                "document_id=%s error_type=%s",
                document_id,
                type(exc).__name__,
            )
