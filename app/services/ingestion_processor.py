"""Shared parse, chunk, embed, and vector-write core for V1 and R23."""

from __future__ import annotations

from pathlib import Path

from app.core.exceptions import DocumentParseError, DocumentStorageError
from app.document_processing.chunker import chunk_sections
from app.document_processing.file_hash import calculate_sha256
from app.document_processing.file_validation import validate_storage_path
from app.document_processing.loaders import load_document
from app.domain.models import Document, DocumentStatus
from app.providers.embedding_provider import EmbeddingProvider
from app.storage.vector_store import VectorStore


class IngestionProcessor:
    """Process an existing Document without owning its business state changes."""

    def __init__(
        self,
        vector_store: VectorStore,
        embedding_provider: EmbeddingProvider,
        upload_dir: Path,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        if embedding_provider.dimensions != vector_store.dimensions:
            raise ValueError("embedding and vector store dimensions must match")
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if not 0 <= chunk_overlap < chunk_size:
            raise ValueError(
                "chunk_overlap must be non-negative and smaller than chunk_size"
            )
        self._vector_store = vector_store
        self._embedding_provider = embedding_provider
        self._upload_dir = upload_dir
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def process(self, document: Document) -> int:
        if document.status is not DocumentStatus.PROCESSING:
            raise ValueError("only processing documents can be ingested")
        stored_path = validate_storage_path(
            self._upload_dir,
            document.document_id,
            document.media_type,
            document.stored_path,
        )
        try:
            actual_size = stored_path.stat().st_size
            actual_sha256 = calculate_sha256(stored_path)
        except OSError as exc:
            raise DocumentStorageError() from exc
        if actual_size != document.size_bytes or actual_sha256 != document.sha256:
            raise DocumentStorageError()

        # A previous process may have died after its upsert but before committing
        # SQLite readiness. Cleaning by document_id makes single-Worker replay safe.
        self._vector_store.delete_by_document(document.document_id)
        sections = load_document(stored_path, document.media_type)
        chunks = chunk_sections(
            sections,
            document_id=document.document_id,
            filename=document.filename,
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
        )
        if not chunks:
            raise DocumentParseError()
        vectors = self._embedding_provider.embed_documents(
            [chunk.text for chunk in chunks]
        )
        self._vector_store.upsert(chunks, vectors)
        return len(chunks)

    def cleanup_vectors(self, document: Document) -> None:
        self._vector_store.delete_by_document(document.document_id)
