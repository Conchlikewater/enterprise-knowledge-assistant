"""Persistence port for asynchronous ingestion jobs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.models import Document, IngestionJob


class IngestionJobRepository(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Create or validate the Job persistence schema."""

    @abstractmethod
    def create_document_and_job(
        self,
        document: Document,
        job: IngestionJob,
    ) -> None:
        """Atomically create one processing document and its pending job."""

    @abstractmethod
    def get_job(self, job_id: UUID) -> IngestionJob | None:
        """Return one ingestion job, or None when absent."""

    @abstractmethod
    def claim_next_job(self) -> IngestionJob | None:
        """Atomically move the oldest eligible pending job to running."""

    @abstractmethod
    def complete_job(
        self,
        job_id: UUID,
        document_id: UUID,
        chunk_count: int,
    ) -> None:
        """Atomically mark the running job and its document ready."""

    @abstractmethod
    def fail_job(
        self,
        job_id: UUID,
        document_id: UUID,
        error_code: str,
    ) -> None:
        """Atomically mark the running job and its document failed."""

    @abstractmethod
    def recover_running_jobs(self) -> int:
        """Return abandoned running jobs to pending during Worker startup."""
