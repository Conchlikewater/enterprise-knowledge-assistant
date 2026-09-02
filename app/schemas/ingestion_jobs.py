"""Public R23 schemas for asynchronous document intake and Job queries."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.models import (
    Document,
    DocumentStatus,
    IngestionJob,
    IngestionJobStatus,
)


class AsyncDocumentAcceptedResponse(BaseModel):
    document_id: UUID
    job_id: UUID
    document_status: DocumentStatus
    job_status: IngestionJobStatus
    status_url: str = Field(pattern=r"^/api/v2/jobs/[0-9a-f-]+$")

    @classmethod
    def from_domain(
        cls,
        document: Document,
        job: IngestionJob,
    ) -> AsyncDocumentAcceptedResponse:
        return cls(
            document_id=document.document_id,
            job_id=job.job_id,
            document_status=document.status,
            job_status=job.status,
            status_url=f"/api/v2/jobs/{job.job_id}",
        )


class IngestionJobResponse(BaseModel):
    job_id: UUID
    document_id: UUID
    status: IngestionJobStatus
    attempt_count: int = Field(ge=0)
    error_code: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    @classmethod
    def from_domain(cls, job: IngestionJob) -> IngestionJobResponse:
        return cls(
            job_id=job.job_id,
            document_id=job.document_id,
            status=job.status,
            attempt_count=job.attempt_count,
            error_code=job.error_code,
            created_at=job.created_at,
            updated_at=job.updated_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )
