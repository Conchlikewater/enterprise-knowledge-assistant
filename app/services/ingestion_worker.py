"""Single-Worker orchestration for persisted asynchronous ingestion jobs."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from time import sleep

from app.core.exceptions import ApplicationError, DocumentRepositoryError
from app.document_processing.file_validation import validate_storage_path
from app.domain.models import (
    Document,
    DocumentStatus,
    IngestionJob,
    IngestionJobStatus,
)
from app.services.ingestion_processor import IngestionProcessor
from app.storage.document_repository import DocumentRepository
from app.storage.ingestion_job_repository import IngestionJobRepository

logger = logging.getLogger(__name__)

AfterUpsertHook = Callable[[IngestionJob], None]


class IngestionWorker:
    """Claim and process one job at a time; multi-Worker ownership is out of scope."""

    def __init__(
        self,
        document_repository: DocumentRepository,
        ingestion_job_repository: IngestionJobRepository,
        processor: IngestionProcessor,
        upload_dir: Path,
        poll_interval_seconds: float,
        after_upsert_hook: AfterUpsertHook | None = None,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self._document_repository = document_repository
        self._ingestion_job_repository = ingestion_job_repository
        self._processor = processor
        self._upload_dir = upload_dir
        self._poll_interval_seconds = poll_interval_seconds
        self._after_upsert_hook = after_upsert_hook

    def recover_abandoned_jobs(self) -> int:
        recovered = self._ingestion_job_repository.recover_running_jobs()
        if recovered:
            logger.warning(
                "event=ingestion_jobs_recovered recovered_count=%d",
                recovered,
            )
        return recovered

    def process_next(self) -> bool:
        """Process at most one job and report whether a job was claimed."""
        job = self._ingestion_job_repository.claim_next_job()
        if job is None:
            return False

        document: Document | None = None
        try:
            document = self._document_repository.get(job.document_id)
            if document is None:
                raise DocumentRepositoryError()
            chunk_count = self._processor.process(document)
            if self._after_upsert_hook is not None:
                self._after_upsert_hook(job)
        except Exception as exc:
            if document is not None:
                self._compensate_failed_processing(document)
            error_code = (
                exc.code if isinstance(exc, ApplicationError) else "INGESTION_FAILED"
            )
            try:
                self._ingestion_job_repository.fail_job(
                    job.job_id,
                    job.document_id,
                    error_code,
                )
            except Exception as state_exc:
                logger.error(
                    "event=ingestion_job_failure_state_update_failed job_id=%s "
                    "document_id=%s error_type=%s",
                    job.job_id,
                    job.document_id,
                    type(state_exc).__name__,
                )
                # Leaving a running Job inside a live Worker would strand it,
                # because startup recovery only runs when the process starts.
                # Exit so the process supervisor can restart the Worker and
                # converge the abandoned state through the same recovery path.
                raise state_exc from exc
            logger.warning(
                "event=ingestion_job_failed job_id=%s document_id=%s "
                "attempt_count=%d error_code=%s error_type=%s",
                job.job_id,
                job.document_id,
                job.attempt_count,
                error_code,
                type(exc).__name__,
            )
            return True

        try:
            self._ingestion_job_repository.complete_job(
                job.job_id,
                job.document_id,
                chunk_count,
            )
        except Exception as exc:
            # A commit can be ambiguous to its caller (for example, the database
            # connection can fail after SQLite made the transaction durable). Do
            # not delete already-written vectors or the source file until the
            # persisted state is known. If completion was not durably committed,
            # crashing the Worker leaves running/processing state for the normal
            # startup recovery path.
            try:
                persisted_job = self._ingestion_job_repository.get_job(job.job_id)
                persisted_document = self._document_repository.get(job.document_id)
            except Exception as verification_exc:
                logger.error(
                    "event=ingestion_job_completion_verification_failed job_id=%s "
                    "document_id=%s completion_error_type=%s "
                    "verification_error_type=%s",
                    job.job_id,
                    job.document_id,
                    type(exc).__name__,
                    type(verification_exc).__name__,
                )
                raise exc from verification_exc

            if (
                persisted_job is not None
                and persisted_job.status is IngestionJobStatus.READY
                and persisted_document is not None
                and persisted_document.status is DocumentStatus.READY
                and persisted_document.chunk_count == chunk_count
            ):
                logger.warning(
                    "event=ingestion_job_completion_confirmed_after_error "
                    "job_id=%s document_id=%s error_type=%s",
                    job.job_id,
                    job.document_id,
                    type(exc).__name__,
                )
            else:
                logger.error(
                    "event=ingestion_job_completion_uncertain job_id=%s "
                    "document_id=%s error_type=%s",
                    job.job_id,
                    job.document_id,
                    type(exc).__name__,
                )
                raise

        logger.info(
            "event=ingestion_job_succeeded job_id=%s document_id=%s "
            "attempt_count=%d chunk_count=%d",
            job.job_id,
            job.document_id,
            job.attempt_count,
            chunk_count,
        )
        return True

    def run_forever(self) -> None:
        self.recover_abandoned_jobs()
        while True:
            if not self.process_next():
                sleep(self._poll_interval_seconds)

    def _compensate_failed_processing(self, document: Document) -> None:
        try:
            self._processor.cleanup_vectors(document)
        except Exception as exc:
            logger.error(
                "event=ingestion_job_vector_compensation_failed document_id=%s "
                "error_type=%s",
                document.document_id,
                type(exc).__name__,
            )
        try:
            stored_path = validate_storage_path(
                self._upload_dir,
                document.document_id,
                document.media_type,
                document.stored_path,
            )
            stored_path.unlink(missing_ok=True)
        except Exception as exc:
            logger.error(
                "event=ingestion_job_file_compensation_failed document_id=%s "
                "error_type=%s",
                document.document_id,
                type(exc).__name__,
            )
