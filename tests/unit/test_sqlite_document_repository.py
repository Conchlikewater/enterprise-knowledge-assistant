import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from app.core.exceptions import DocumentConflictError, DocumentNotFoundError
from app.domain.models import Document, DocumentStatus
from app.storage.sqlite_document_repository import SQLiteDocumentRepository


class SQLiteDocumentRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        database_path = Path(self._temporary_directory.name) / "nested" / "test.db"
        self.repository = SQLiteDocumentRepository(database_path)
        self.repository.initialize()

    @staticmethod
    def _document(sha256: str = "a" * 64) -> Document:
        return Document(
            document_id=uuid4(),
            filename="policy.pdf",
            media_type="application/pdf",
            size_bytes=1024,
            sha256=sha256,
            status=DocumentStatus.PROCESSING,
            stored_path=Path("data/uploads/internal-name.pdf"),
        )

    def test_initialize_creates_a_healthy_repository(self) -> None:
        self.assertTrue(self.repository.health())

    def test_document_lifecycle(self) -> None:
        document = self._document()

        self.repository.create(document)
        stored = self.repository.get(document.document_id)
        self.assertEqual(stored, document)
        self.assertEqual(self.repository.list(), (document,))

        self.repository.update_status(document.document_id, DocumentStatus.READY, 3)
        updated = self.repository.get(document.document_id)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, DocumentStatus.READY)
        self.assertEqual(updated.chunk_count, 3)
        self.assertGreaterEqual(updated.updated_at, document.updated_at)

        self.repository.delete(document.document_id)
        self.assertIsNone(self.repository.get(document.document_id))

    def test_duplicate_content_hash_is_a_conflict(self) -> None:
        first = self._document(sha256="b" * 64)
        second = self._document(sha256="b" * 64)
        self.repository.create(first)

        with self.assertRaises(DocumentConflictError):
            self.repository.create(second)

    def test_missing_updates_and_deletes_are_not_found(self) -> None:
        missing_id = uuid4()

        with self.assertRaises(DocumentNotFoundError):
            self.repository.update_status(missing_id, DocumentStatus.FAILED, 0)
        with self.assertRaises(DocumentNotFoundError):
            self.repository.delete(missing_id)


if __name__ == "__main__":
    unittest.main()
