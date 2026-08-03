import tempfile
import unittest
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from uuid import UUID

from app.core.exceptions import (
    DocumentConflictError,
    DocumentParseError,
    FileTooLargeError,
    UnsupportedFileTypeError,
    VectorStoreError,
)
from app.domain.models import Chunk, DocumentStatus, RetrievalResult
from app.providers.embedding_provider import EmbeddingProvider
from app.services.ingestion_service import IngestionService
from app.storage.qdrant_vector_store import QdrantVectorStore
from app.storage.sqlite_document_repository import SQLiteDocumentRepository
from app.storage.vector_store import VectorStore


class FakeEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimensions: int = 3) -> None:
        self._dimensions = dimensions

    @property
    def name(self) -> str:
        return "fake"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def close(self) -> None:
        pass

    def _vector(self, text: str) -> list[float]:
        return [1.0, float(len(text) % 5) / 10.0, 0.0]


class FailAfterUpsertVectorStore(VectorStore):
    def __init__(self, delegate: VectorStore) -> None:
        self._delegate = delegate

    @property
    def dimensions(self) -> int:
        return self._delegate.dimensions

    def initialize(self) -> None:
        self._delegate.initialize()

    def health(self) -> bool:
        return self._delegate.health()

    def upsert(
        self,
        chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        self._delegate.upsert(chunks, vectors)
        raise VectorStoreError()

    def search(
        self,
        query_vector: Sequence[float],
        document_ids: Sequence[UUID],
        limit: int,
    ) -> list[RetrievalResult]:
        return self._delegate.search(query_vector, document_ids, limit)

    def delete_by_document(self, document_id: UUID) -> None:
        self._delegate.delete_by_document(document_id)

    def close(self) -> None:
        self._delegate.close()


class IngestionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name)
        self.upload_dir = self.root / "uploads"
        self.repository = SQLiteDocumentRepository(self.root / "app.db")
        self.repository.initialize()
        self.vector_store = QdrantVectorStore(
            storage_path=self.root / "qdrant",
            collection_name="test_chunks",
            vector_size=3,
        )
        self.vector_store.initialize()
        self.provider = FakeEmbeddingProvider()
        self.service = self._new_service(self.vector_store)

    def tearDown(self) -> None:
        self.vector_store.close()

    def _new_service(self, vector_store: VectorStore) -> IngestionService:
        return IngestionService(
            document_repository=self.repository,
            vector_store=vector_store,
            embedding_provider=self.provider,
            upload_dir=self.upload_dir,
            max_upload_bytes=1024,
            chunk_size=32,
            chunk_overlap=5,
        )

    def test_txt_ingestion_reaches_ready_and_is_searchable(self) -> None:
        private_text = "INTERNAL_ONLY_MARKER alpha policy evidence for retrieval."

        with self.assertLogs("app.services.ingestion_service", level="INFO") as logs:
            document = self.service.ingest(
                BytesIO(private_text.encode("utf-8")),
                filename="policy.txt",
                media_type="text/plain",
            )

        self.assertEqual(document.status, DocumentStatus.READY)
        self.assertGreater(document.chunk_count, 0)
        self.assertTrue(document.stored_path.exists())
        results = self.vector_store.search(
            self.provider.embed_query("synthetic query"),
            [document.document_id],
            limit=10,
        )
        self.assertEqual(len(results), document.chunk_count)
        self.assertTrue(all(item.document_id == document.document_id for item in results))
        self.assertNotIn(private_text, "\n".join(logs.output))

    def test_duplicate_content_keeps_only_the_first_ready_document(self) -> None:
        content = b"duplicate policy evidence"
        first = self.service.ingest(BytesIO(content), "first.txt", "text/plain")

        with self.assertRaises(DocumentConflictError):
            self.service.ingest(BytesIO(content), "second.txt", "text/plain")

        documents = self.repository.list()
        self.assertEqual([item.document_id for item in documents], [first.document_id])
        self.assertEqual(documents[0].status, DocumentStatus.READY)
        self.assertEqual(list(self.upload_dir.iterdir()), [first.stored_path])

    def test_parse_failure_marks_record_failed_and_removes_file_and_vectors(self) -> None:
        with self.assertRaises(DocumentParseError):
            self.service.ingest(BytesIO(b"   \n"), "blank.txt", "text/plain")

        documents = self.repository.list()
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].status, DocumentStatus.FAILED)
        self.assertEqual(documents[0].chunk_count, 0)
        self.assertFalse(documents[0].stored_path.exists())
        self.assertEqual(
            self.vector_store.search([1.0, 0.0, 0.0], [documents[0].document_id], 5),
            [],
        )

    def test_partial_vector_write_is_compensated(self) -> None:
        failing_store = FailAfterUpsertVectorStore(self.vector_store)
        service = self._new_service(failing_store)

        with self.assertRaises(VectorStoreError):
            service.ingest(
                BytesIO(b"enough content to create and index one chunk"),
                "failure.txt",
                "text/plain",
            )

        document = self.repository.list()[0]
        self.assertEqual(document.status, DocumentStatus.FAILED)
        self.assertFalse(document.stored_path.exists())
        self.assertEqual(
            self.vector_store.search([1.0, 0.0, 0.0], [document.document_id], 5),
            [],
        )

    def test_rejected_metadata_and_size_create_no_records_or_files(self) -> None:
        cases = (
            (
                lambda: self.service.ingest(
                    BytesIO(b"unsupported"), "notes.md", "text/markdown"
                ),
                UnsupportedFileTypeError,
            ),
            (
                lambda: self.service.ingest(
                    BytesIO(b"x" * 1025), "large.txt", "text/plain"
                ),
                FileTooLargeError,
            ),
        )

        for action, expected_error in cases:
            with self.subTest(expected_error=expected_error.__name__):
                with self.assertRaises(expected_error):
                    action()

        self.assertEqual(self.repository.list(), ())
        self.assertTrue(
            not self.upload_dir.exists() or list(self.upload_dir.iterdir()) == []
        )

    def test_dimension_mismatch_is_rejected_before_ingestion(self) -> None:
        with self.assertRaises(ValueError):
            IngestionService(
                document_repository=self.repository,
                vector_store=self.vector_store,
                embedding_provider=FakeEmbeddingProvider(dimensions=2),
                upload_dir=self.upload_dir,
                max_upload_bytes=1024,
                chunk_size=32,
                chunk_overlap=5,
            )


if __name__ == "__main__":
    unittest.main()
