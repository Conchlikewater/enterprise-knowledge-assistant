import tempfile
import unittest
from pathlib import Path
from uuid import UUID, uuid4

from app.core.exceptions import DocumentNotFoundError, DocumentStorageError
from app.document_processing.file_validation import build_storage_path
from app.domain.models import Document, DocumentStatus
from app.services.document_service import DocumentService
from app.storage.sqlite_document_repository import SQLiteDocumentRepository
from app.storage.vector_store import VectorStore


class RecordingVectorStore(VectorStore):
    def __init__(self) -> None:
        self.deleted_document_ids: list[UUID] = []

    @property
    def dimensions(self) -> int:
        return 3

    def initialize(self) -> None:
        pass

    def health(self) -> bool:
        return True

    def upsert(self, chunks, vectors) -> None:
        raise NotImplementedError

    def search(self, query_vector, document_ids, limit):
        raise NotImplementedError

    def delete_by_document(self, document_id: UUID) -> None:
        self.deleted_document_ids.append(document_id)

    def close(self) -> None:
        pass


class DocumentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name)
        self.upload_dir = self.root / "uploads"
        self.repository = SQLiteDocumentRepository(self.root / "app.db")
        self.repository.initialize()
        self.vector_store = RecordingVectorStore()
        self.service = DocumentService(
            document_repository=self.repository,
            vector_store=self.vector_store,
            upload_dir=self.upload_dir,
        )

    def test_safe_document_is_deleted_from_all_local_stores(self) -> None:
        document_id = uuid4()
        stored_path = build_storage_path(self.upload_dir, document_id, ".txt")
        stored_path.parent.mkdir(parents=True)
        stored_path.write_text("safe content", encoding="utf-8")
        document = self._document(document_id, stored_path)
        self.repository.create(document)

        self.service.delete_document(document_id)

        self.assertEqual(self.vector_store.deleted_document_ids, [document_id])
        self.assertFalse(stored_path.exists())
        self.assertIsNone(self.repository.get(document_id))

    def test_missing_document_is_rejected_before_vector_deletion(self) -> None:
        with self.assertRaises(DocumentNotFoundError):
            self.service.delete_document(uuid4())

        self.assertEqual(self.vector_store.deleted_document_ids, [])

    def test_tampered_stored_path_cannot_delete_an_external_file(self) -> None:
        document_id = uuid4()
        external_path = self.root / "must-not-delete.txt"
        external_path.write_text("keep", encoding="utf-8")
        document = self._document(document_id, external_path)
        self.repository.create(document)

        with self.assertRaises(DocumentStorageError):
            self.service.delete_document(document_id)

        self.assertTrue(external_path.exists())
        self.assertIsNotNone(self.repository.get(document_id))
        self.assertEqual(self.vector_store.deleted_document_ids, [])

    @staticmethod
    def _document(document_id: UUID, stored_path: Path) -> Document:
        return Document(
            document_id=document_id,
            filename="policy.txt",
            media_type="text/plain",
            size_bytes=12,
            sha256="a" * 64,
            status=DocumentStatus.READY,
            stored_path=stored_path,
            chunk_count=1,
        )


if __name__ == "__main__":
    unittest.main()
