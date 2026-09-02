import tempfile
import unittest
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from uuid import UUID

from app.core.exceptions import DocumentRepositoryError, VectorStoreError
from app.domain.models import (
    Chunk,
    DocumentStatus,
    IngestionJob,
    IngestionJobStatus,
    RetrievalResult,
)
from app.services.async_ingestion_service import AsyncIngestionService
from app.services.ingestion_processor import IngestionProcessor
from app.services.ingestion_worker import IngestionWorker
from app.storage.qdrant_vector_store import QdrantVectorStore
from app.storage.sqlite_document_repository import SQLiteDocumentRepository
from app.storage.vector_store import VectorStore
from tests.fakes import DeterministicEmbeddingProvider


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


class CommitThenRaiseRepository(SQLiteDocumentRepository):
    """Simulate a caller seeing an error after SQLite made completion durable."""

    def complete_job(
        self,
        job_id: UUID,
        document_id: UUID,
        chunk_count: int,
    ) -> None:
        super().complete_job(job_id, document_id, chunk_count)
        raise DocumentRepositoryError()


class FailBeforeCommitRepository(SQLiteDocumentRepository):
    """Simulate completion failing before the ready transaction is durable."""

    def complete_job(
        self,
        job_id: UUID,
        document_id: UUID,
        chunk_count: int,
    ) -> None:
        raise DocumentRepositoryError()


class FailFailureStateRepository(SQLiteDocumentRepository):
    """Simulate SQLite being unavailable while recording a processing failure."""

    def fail_job(
        self,
        job_id: UUID,
        document_id: UUID,
        error_code: str,
    ) -> None:
        raise DocumentRepositoryError()


class AsyncIngestionWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name)
        self.upload_dir = self.root / "uploads"
        self.repository = SQLiteDocumentRepository(self.root / "app.db")
        self.repository.initialize()
        self.vector_store = QdrantVectorStore(
            storage_path=self.root / "qdrant",
            collection_name="async_worker_chunks",
            vector_size=3,
        )
        self.vector_store.initialize()
        self.provider = DeterministicEmbeddingProvider()
        self.submitter = AsyncIngestionService(
            ingestion_job_repository=self.repository,
            upload_dir=self.upload_dir,
            max_upload_bytes=4096,
        )

    def tearDown(self) -> None:
        self.vector_store.close()

    def _worker(
        self,
        vector_store: VectorStore | None = None,
        after_upsert_hook=None,
        repository: SQLiteDocumentRepository | None = None,
    ) -> IngestionWorker:
        resolved_repository = repository or self.repository
        processor = IngestionProcessor(
            vector_store=vector_store or self.vector_store,
            embedding_provider=self.provider,
            upload_dir=self.upload_dir,
            chunk_size=32,
            chunk_overlap=5,
        )
        return IngestionWorker(
            document_repository=resolved_repository,
            ingestion_job_repository=resolved_repository,
            processor=processor,
            upload_dir=self.upload_dir,
            poll_interval_seconds=0.01,
            after_upsert_hook=after_upsert_hook,
        )

    def test_submission_is_fast_state_only_until_worker_processes_it(self) -> None:
        document, job = self.submitter.submit(
            BytesIO(b"Asynchronous policy evidence."),
            "policy.txt",
            "text/plain",
        )

        self.assertEqual(document.status, DocumentStatus.PROCESSING)
        self.assertEqual(job.status, IngestionJobStatus.PENDING)
        self.assertEqual(self.provider.embedded_document_batches, [])
        self.assertTrue(document.stored_path.exists())

        self.assertTrue(self._worker().process_next())

        ready_job = self.repository.get_job(job.job_id)
        ready_document = self.repository.get(document.document_id)
        self.assertEqual(ready_job.status, IngestionJobStatus.READY)
        self.assertEqual(ready_job.attempt_count, 1)
        self.assertEqual(ready_document.status, DocumentStatus.READY)
        self.assertGreater(ready_document.chunk_count, 0)
        self.assertEqual(len(self.provider.embedded_document_batches), 1)
        self.assertFalse(self._worker().process_next())

    def test_fixed_crash_point_recovers_without_duplicate_visible_chunks(self) -> None:
        document, job = self.submitter.submit(
            BytesIO(
                b"First evidence sentence. Second evidence sentence. "
                b"Third evidence sentence."
            ),
            "recovery.txt",
            "text/plain",
        )

        def crash_after_upsert(_: IngestionJob) -> None:
            raise SystemExit(91)

        with self.assertRaises(SystemExit):
            self._worker(after_upsert_hook=crash_after_upsert).process_next()

        crashed_job = self.repository.get_job(job.job_id)
        crashed_document = self.repository.get(document.document_id)
        self.assertEqual(crashed_job.status, IngestionJobStatus.RUNNING)
        self.assertEqual(crashed_job.attempt_count, 1)
        self.assertEqual(crashed_document.status, DocumentStatus.PROCESSING)
        partial_results = self.vector_store.search(
            [1.0, 0.0, 0.0],
            [document.document_id],
            limit=100,
        )
        self.assertGreater(len(partial_results), 0)

        restarted_worker = self._worker()
        self.assertEqual(restarted_worker.recover_abandoned_jobs(), 1)
        self.assertTrue(restarted_worker.process_next())

        recovered_job = self.repository.get_job(job.job_id)
        recovered_document = self.repository.get(document.document_id)
        recovered_results = self.vector_store.search(
            [1.0, 0.0, 0.0],
            [document.document_id],
            limit=100,
        )
        self.assertEqual(recovered_job.status, IngestionJobStatus.READY)
        self.assertEqual(recovered_job.attempt_count, 2)
        self.assertEqual(recovered_document.status, DocumentStatus.READY)
        self.assertEqual(len(recovered_results), recovered_document.chunk_count)
        self.assertEqual(
            len({result.chunk_id for result in recovered_results}),
            len(recovered_results),
        )

    def test_partial_qdrant_write_is_compensated_and_job_fails_safely(self) -> None:
        document, job = self.submitter.submit(
            BytesIO(b"Evidence that reaches Qdrant before a controlled failure."),
            "partial.txt",
            "text/plain",
        )
        failing_store = FailAfterUpsertVectorStore(self.vector_store)

        self.assertTrue(self._worker(vector_store=failing_store).process_next())

        failed_job = self.repository.get_job(job.job_id)
        failed_document = self.repository.get(document.document_id)
        self.assertEqual(failed_job.status, IngestionJobStatus.FAILED)
        self.assertEqual(failed_job.error_code, "VECTOR_STORE_ERROR")
        self.assertEqual(failed_document.status, DocumentStatus.FAILED)
        self.assertFalse(document.stored_path.exists())
        self.assertEqual(
            self.vector_store.search(
                [1.0, 0.0, 0.0],
                [document.document_id],
                limit=100,
            ),
            [],
        )

    def test_completion_error_after_commit_does_not_delete_ready_data(self) -> None:
        document, job = self.submitter.submit(
            BytesIO(b"Evidence remains available after an ambiguous commit."),
            "committed.txt",
            "text/plain",
        )
        repository = CommitThenRaiseRepository(self.root / "app.db")

        with self.assertLogs("app.services.ingestion_worker", level="WARNING") as logs:
            self.assertTrue(self._worker(repository=repository).process_next())

        ready_job = self.repository.get_job(job.job_id)
        ready_document = self.repository.get(document.document_id)
        results = self.vector_store.search(
            [1.0, 0.0, 0.0],
            [document.document_id],
            limit=100,
        )
        self.assertEqual(ready_job.status, IngestionJobStatus.READY)
        self.assertEqual(ready_document.status, DocumentStatus.READY)
        self.assertTrue(document.stored_path.exists())
        self.assertEqual(len(results), ready_document.chunk_count)
        self.assertIn("completion_confirmed_after_error", logs.output[0])

    def test_failure_state_update_error_exits_and_startup_recovery_converges(
        self,
    ) -> None:
        document, job = self.submitter.submit(
            BytesIO(b"A controlled vector failure followed by a SQLite failure."),
            "failure-state.txt",
            "text/plain",
        )
        repository = FailFailureStateRepository(self.root / "app.db")
        failing_store = FailAfterUpsertVectorStore(self.vector_store)

        with self.assertRaises(DocumentRepositoryError):
            self._worker(
                vector_store=failing_store,
                repository=repository,
            ).process_next()

        self.assertEqual(
            self.repository.get_job(job.job_id).status,
            IngestionJobStatus.RUNNING,
        )
        self.assertEqual(
            self.repository.get(document.document_id).status,
            DocumentStatus.PROCESSING,
        )
        self.assertFalse(document.stored_path.exists())

        restarted_worker = self._worker()
        self.assertEqual(restarted_worker.recover_abandoned_jobs(), 1)
        self.assertTrue(restarted_worker.process_next())
        failed_job = self.repository.get_job(job.job_id)
        failed_document = self.repository.get(document.document_id)
        self.assertEqual(failed_job.status, IngestionJobStatus.FAILED)
        self.assertEqual(failed_job.error_code, "DOCUMENT_STORAGE_ERROR")
        self.assertEqual(failed_document.status, DocumentStatus.FAILED)

    def test_completion_error_before_commit_is_left_for_restart_recovery(
        self,
    ) -> None:
        document, job = self.submitter.submit(
            BytesIO(b"Evidence remains replayable when completion cannot commit."),
            "uncommitted.txt",
            "text/plain",
        )
        repository = FailBeforeCommitRepository(self.root / "app.db")

        with self.assertRaises(DocumentRepositoryError):
            self._worker(repository=repository).process_next()

        running_job = self.repository.get_job(job.job_id)
        processing_document = self.repository.get(document.document_id)
        partial_results = self.vector_store.search(
            [1.0, 0.0, 0.0],
            [document.document_id],
            limit=100,
        )
        self.assertEqual(running_job.status, IngestionJobStatus.RUNNING)
        self.assertEqual(processing_document.status, DocumentStatus.PROCESSING)
        self.assertTrue(document.stored_path.exists())
        self.assertGreater(len(partial_results), 0)

        restarted_worker = self._worker()
        self.assertEqual(restarted_worker.recover_abandoned_jobs(), 1)
        self.assertTrue(restarted_worker.process_next())
        self.assertEqual(
            self.repository.get_job(job.job_id).status,
            IngestionJobStatus.READY,
        )
        self.assertEqual(
            self.repository.get(document.document_id).status,
            DocumentStatus.READY,
        )


if __name__ == "__main__":
    unittest.main()
