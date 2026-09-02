"""Fast asynchronous intake: validate, store, and atomically create a Job."""

from __future__ import annotations

import logging
from pathlib import Path
from time import monotonic
from typing import BinaryIO
from uuid import UUID, uuid4

from app.core.exceptions import IngestionJobNotFoundError
from app.document_processing.file_storage import save_upload_stream
from app.document_processing.file_validation import (
    build_storage_path,
    validate_file,
    validate_file_identity,
)
from app.domain.models import (
    Document,
    DocumentStatus,
    IngestionJob,
    IngestionJobStatus,
)
from app.storage.ingestion_job_repository import IngestionJobRepository

logger = logging.getLogger(__name__)


class AsyncIngestionService:
    def __init__(
        self,
        ingestion_job_repository: IngestionJobRepository,
        upload_dir: Path,
        max_upload_bytes: int,
    ) -> None:
        if max_upload_bytes <= 0:
            raise ValueError("max_upload_bytes must be positive")
        self._ingestion_job_repository = ingestion_job_repository
        self._upload_dir = upload_dir
        self._max_upload_bytes = max_upload_bytes

    def submit(
        self,
        source: BinaryIO,
        filename: str,
        media_type: str,
    ) -> tuple[Document, IngestionJob]:
        """Persist only the bounded upload and pending business state."""
        identity = validate_file_identity(filename, media_type)
        document_id = uuid4()
        job_id = uuid4()
        stored_path = build_storage_path(
            self._upload_dir,
            document_id,
            identity.suffix,
        )
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
            job = IngestionJob(
                job_id=job_id,
                document_id=document_id,
                status=IngestionJobStatus.PENDING,
            )
            self._ingestion_job_repository.create_document_and_job(document, job)
            logger.info(
                "event=async_ingestion_submitted document_id=%s job_id=%s "
                "media_type=%s size_bytes=%d elapsed_ms=%d",
                document_id,
                job_id,
                validated_file.media_type,
                validated_file.size_bytes,
                int((monotonic() - started_at) * 1000),
            )
            return document, job
        except Exception as exc:
            self._remove_stored_file(stored_path, document_id)
            logger.warning(
                "event=async_ingestion_submission_failed document_id=%s job_id=%s "
                "media_type=%s error_type=%s elapsed_ms=%d",
                document_id,
                job_id,
                identity.media_type,
                type(exc).__name__,
                int((monotonic() - started_at) * 1000),
            )
            raise

    def get_job(self, job_id: UUID) -> IngestionJob:
        job = self._ingestion_job_repository.get_job(job_id)
        if job is None:
            raise IngestionJobNotFoundError()
        return job

    @staticmethod
    def _remove_stored_file(stored_path: Path, document_id: UUID) -> None:
        try:
            stored_path.unlink(missing_ok=True)
        except OSError as exc:
            logger.error(
                "event=async_ingestion_file_rollback_failed "
                "document_id=%s error_type=%s",
                document_id,
                type(exc).__name__,
            )
