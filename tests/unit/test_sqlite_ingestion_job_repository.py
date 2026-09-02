import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from app.core.exceptions import (
    DocumentConflictError,
    DocumentProcessingError,
    DocumentRepositoryError,
    IngestionJobStateError,
)
from app.domain.models import (
    Document,
    DocumentStatus,
    IngestionJob,
    IngestionJobStatus,
)
from app.storage.sqlite_document_repository import (
    SCHEMA_VERSION,
    SQLiteDocumentRepository,
)


class SQLiteIngestionJobRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.database_path = Path(self._temporary_directory.name) / "app.db"
        self.repository = SQLiteDocumentRepository(self.database_path)
        self.repository.initialize()

    @staticmethod
    def _document(sha256: str = "a" * 64) -> Document:
        document_id = uuid4()
        return Document(
            document_id=document_id,
            filename="policy.txt",
            media_type="text/plain",
            size_bytes=12,
            sha256=sha256,
            status=DocumentStatus.PROCESSING,
            stored_path=Path(f"data/uploads/{document_id}.txt"),
        )

    @staticmethod
    def _job(document: Document) -> IngestionJob:
        return IngestionJob(
            job_id=uuid4(),
            document_id=document.document_id,
            status=IngestionJobStatus.PENDING,
        )

    def test_schema_v2_uses_wal_and_preserves_a_legacy_document(self) -> None:
        legacy_path = Path(self._temporary_directory.name) / "legacy.db"
        legacy_document = self._document()
        with closing(sqlite3.connect(legacy_path)) as connection, connection:
            connection.execute(
                """
                CREATE TABLE documents (
                    document_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    stored_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(legacy_document.document_id),
                    legacy_document.filename,
                    legacy_document.media_type,
                    legacy_document.size_bytes,
                    legacy_document.sha256,
                    legacy_document.status.value,
                    legacy_document.chunk_count,
                    str(legacy_document.stored_path),
                    legacy_document.created_at.isoformat(),
                    legacy_document.updated_at.isoformat(),
                ),
            )

        migrated = SQLiteDocumentRepository(legacy_path)
        migrated.initialize()

        self.assertEqual(migrated.get(legacy_document.document_id), legacy_document)
        with closing(sqlite3.connect(legacy_path)) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION
            )
            self.assertEqual(
                connection.execute("PRAGMA journal_mode").fetchone()[0], "wal"
            )
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'ingestion_jobs'"
            ).fetchone()
        self.assertIsNotNone(table)

    def test_document_and_job_lifecycle_is_atomic(self) -> None:
        document = self._document()
        job = self._job(document)
        self.repository.create_document_and_job(document, job)

        claimed = self.repository.claim_next_job()

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.job_id, job.job_id)
        self.assertEqual(claimed.status, IngestionJobStatus.RUNNING)
        self.assertEqual(claimed.attempt_count, 1)
        self.assertIsNotNone(claimed.started_at)
        self.assertIsNone(self.repository.claim_next_job())

        self.repository.complete_job(job.job_id, document.document_id, chunk_count=3)
        ready_job = self.repository.get_job(job.job_id)
        ready_document = self.repository.get(document.document_id)
        self.assertEqual(ready_job.status, IngestionJobStatus.READY)
        self.assertIsNotNone(ready_job.completed_at)
        self.assertEqual(ready_document.status, DocumentStatus.READY)
        self.assertEqual(ready_document.chunk_count, 3)

        self.repository.get_for_deletion(document.document_id)
        self.repository.delete(document.document_id)
        self.assertIsNone(self.repository.get_job(job.job_id))

    def test_active_document_cannot_be_deleted(self) -> None:
        document = self._document()
        job = self._job(document)
        self.repository.create_document_and_job(document, job)

        with self.assertRaises(DocumentProcessingError):
            self.repository.get_for_deletion(document.document_id)

        self.assertEqual(self.repository.get(document.document_id), document)
        self.assertEqual(self.repository.get_job(job.job_id), job)

    def test_failure_updates_job_and_document_together(self) -> None:
        document = self._document()
        job = self._job(document)
        self.repository.create_document_and_job(document, job)
        self.repository.claim_next_job()

        self.repository.fail_job(job.job_id, document.document_id, "VECTOR_STORE_ERROR")

        failed_job = self.repository.get_job(job.job_id)
        failed_document = self.repository.get(document.document_id)
        self.assertEqual(failed_job.status, IngestionJobStatus.FAILED)
        self.assertEqual(failed_job.error_code, "VECTOR_STORE_ERROR")
        self.assertEqual(failed_document.status, DocumentStatus.FAILED)
        self.assertEqual(failed_document.chunk_count, 0)

    def test_invalid_completion_rolls_back_both_records(self) -> None:
        document = self._document()
        job = self._job(document)
        self.repository.create_document_and_job(document, job)
        self.repository.claim_next_job()

        with self.assertRaises(IngestionJobStateError):
            self.repository.complete_job(job.job_id, uuid4(), chunk_count=2)

        stored_job = self.repository.get_job(job.job_id)
        stored_document = self.repository.get(document.document_id)
        self.assertEqual(stored_job.status, IngestionJobStatus.RUNNING)
        self.assertEqual(stored_document.status, DocumentStatus.PROCESSING)

    def test_worker_startup_recovers_running_job_without_resetting_attempts(
        self,
    ) -> None:
        document = self._document()
        job = self._job(document)
        self.repository.create_document_and_job(document, job)
        self.repository.claim_next_job()

        self.assertEqual(self.repository.recover_running_jobs(), 1)
        recovered = self.repository.get_job(job.job_id)
        self.assertEqual(recovered.status, IngestionJobStatus.PENDING)
        self.assertEqual(recovered.attempt_count, 1)
        self.assertIsNone(recovered.started_at)

        claimed_again = self.repository.claim_next_job()
        self.assertEqual(claimed_again.attempt_count, 2)

    def test_duplicate_sha_rolls_back_new_job_and_document(self) -> None:
        original = self._document(sha256="b" * 64)
        self.repository.create(original)
        duplicate = self._document(sha256="b" * 64)
        duplicate_job = self._job(duplicate)

        with self.assertRaises(DocumentConflictError):
            self.repository.create_document_and_job(duplicate, duplicate_job)

        self.assertEqual(self.repository.list(), (original,))
        self.assertIsNone(self.repository.get_job(duplicate_job.job_id))

    def test_busy_timeout_waits_for_a_short_lock_then_succeeds(self) -> None:
        repository = SQLiteDocumentRepository(self.database_path, busy_timeout_ms=500)
        document = self._document(sha256="c" * 64)
        result: list[Exception | None] = []
        lock_connection = sqlite3.connect(self.database_path)
        lock_connection.execute("BEGIN IMMEDIATE")

        def create_document() -> None:
            try:
                repository.create(document)
                result.append(None)
            except Exception as exc:  # pragma: no cover - assertion reports the type
                result.append(exc)

        thread = threading.Thread(target=create_document)
        thread.start()
        time.sleep(0.05)
        lock_connection.rollback()
        lock_connection.close()
        thread.join(timeout=2)

        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [None])
        self.assertIsNotNone(repository.get(document.document_id))

    def test_busy_timeout_fails_safely_when_lock_outlives_the_limit(self) -> None:
        repository = SQLiteDocumentRepository(self.database_path, busy_timeout_ms=30)
        lock_connection = sqlite3.connect(self.database_path)
        lock_connection.execute("BEGIN IMMEDIATE")
        try:
            with self.assertRaises(DocumentRepositoryError):
                repository.create(self._document(sha256="d" * 64))
        finally:
            lock_connection.rollback()
            lock_connection.close()

    def test_conditional_claim_allows_only_one_owner(self) -> None:
        document = self._document(sha256="e" * 64)
        job = self._job(document)
        self.repository.create_document_and_job(document, job)
        repositories = (
            SQLiteDocumentRepository(self.database_path, busy_timeout_ms=500),
            SQLiteDocumentRepository(self.database_path, busy_timeout_ms=500),
        )
        barrier = threading.Barrier(3)
        claimed_jobs: list[IngestionJob | None] = []

        def claim(repository: SQLiteDocumentRepository) -> None:
            barrier.wait()
            claimed_jobs.append(repository.claim_next_job())

        threads = [
            threading.Thread(target=claim, args=(repository,))
            for repository in repositories
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=2)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(sum(claimed is not None for claimed in claimed_jobs), 1)
        claimed = next(item for item in claimed_jobs if item is not None)
        self.assertEqual(claimed.job_id, job.job_id)


if __name__ == "__main__":
    unittest.main()
